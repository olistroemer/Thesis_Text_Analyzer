"""Cohort report (SDD Sec. 9.8, ADR-0016 rev. 2, US-PROF-INSIGHTS).

Two pure halves, both stdlib-only:

* ``collect(repo)`` aggregates ``v_current_metrics`` over local,
  non-excluded theses; garbled extractions are dropped from the
  aggregates and counted in a caption.
* ``render_html(data)`` returns one complete, self-contained HTML
  document as a string - every style rule and every chart inline, no
  script, no web font, no external request of any kind (QA-PRIV).

Charts are hand-rolled SVG. The two statistics matplotlib used to
supply are reimplemented here as ``box_stats`` (1.5 x IQR fences,
whiskers to the most extreme datum inside the fence) and ``histogram``
(equal-width bins, last bin closed on both ends).

Nothing here writes a file or opens a browser - the adapters own those
side effects (ADR-0002). Nothing here renders an identifying value:
``notable`` carries thesis ids, never ``pdf_filename``, so the report is
free of PII by construction (ADR-0016 rev. 2, Sec. 9.8.3).
"""

from __future__ import annotations

import html
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import tta
from tta.core.db.repository import Repository

TRUSTWORTHY_METRICS = ("avg_word_len", "std_sentence_len", "yules_k", "flesch_reading_ease")

#: Where adapters put the generated file, relative to the project (Sec. 9.8.3).
REPORTS_DIRNAME = "reports"


def default_report_path(project_dir: Path | str, today: date | None = None) -> Path:
    """``<project>/reports/report-<YYYY-MM-DD>.html`` (Sec. 9.8.3).

    Pure path arithmetic so both adapters land on the same file: the caller
    creates the directory and writes the bytes (ADR-0002 - core does no
    I/O). A same-day file is overwritten; a report is derived data, unlike
    an export, which refuses to overwrite."""
    stamp = today or date.today()
    return Path(project_dir) / REPORTS_DIRNAME / f"report-{stamp:%Y-%m-%d}.html"


@dataclass
class ReportData:
    theses: int = 0
    excluded: int = 0
    garbled: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_language: dict[str, int] = field(default_factory=dict)
    median_words: float | None = None
    year_range: tuple[int, int] | None = None
    # chart series, keyed by thesis id
    words_by_year: list[tuple[int, float, str]] = field(default_factory=list)  # (year, words, type)
    words_by_type: dict[str, list[float]] = field(default_factory=dict)
    fre_by_language: dict[str, list[float]] = field(default_factory=dict)
    notable: list[tuple[str, list[str]]] = field(default_factory=list)  # (label, metrics)


def collect(repo: Repository) -> ReportData:
    theses = {t.id: t for t in repo.list_theses(local_only=True, include_excluded=True)}
    data = ReportData(excluded=sum(t.excluded for t in theses.values()))
    included = {tid: t for tid, t in theses.items() if not t.excluded}

    values: dict[int, dict[str, float | str]] = {tid: {} for tid in included}
    for row in repo.current_metrics():
        if row["thesis_id"] in values and row["metric_name"] is not None:
            value = row["value_num"] if row["value_num"] is not None else row["value_text"]
            values[row["thesis_id"]][row["metric_name"]] = value

    garbled_ids = {
        tid for tid, v in values.items() if v.get("extraction_quality") == "garbled"
    }
    data.garbled = len(garbled_ids)
    usable = {tid: v for tid, v in values.items() if tid not in garbled_ids}
    data.theses = len(usable)

    words = []
    years = []
    for tid, v in usable.items():
        # thesis type is the detected `thesis_type` metric now (ADR-0019, #9);
        # theses with no detected type group under "unspecified"
        detected_type = v.get("thesis_type")
        thesis_type = detected_type if isinstance(detected_type, str) else "unspecified"
        data.by_type[thesis_type] = data.by_type.get(thesis_type, 0) + 1
        language = v.get("language_code")
        if isinstance(language, str):
            data.by_language[language] = data.by_language.get(language, 0) + 1
        word_count = v.get("word_count")
        # length-over-time uses the fused publication_year (#17, SDD Sec. 9.8),
        # not the raw PDF creation_year
        year = v.get("publication_year")
        if isinstance(word_count, (int, float)):
            words.append(word_count)
            data.words_by_type.setdefault(thesis_type, []).append(word_count)
            if isinstance(year, (int, float)):
                data.words_by_year.append((int(year), word_count, thesis_type))
                years.append(int(year))
        fre = v.get("flesch_reading_ease")
        if isinstance(fre, (int, float)) and isinstance(language, str):
            data.fre_by_language.setdefault(language, []).append(fre)
    if words:
        data.median_words = statistics.median(words)
    if years:
        data.year_range = (min(years), max(years))

    # notable theses: IQR outlier on >= 2 trustworthy metrics (Sec. 9.8.3)
    bounds = {}
    for metric in TRUSTWORTHY_METRICS:
        series = [v[metric] for v in usable.values() if isinstance(v.get(metric), (int, float))]
        if len(series) >= 4:
            q1, _, q3 = statistics.quantiles(series, n=4, method="inclusive")
            iqr = q3 - q1
            bounds[metric] = (q1 - 1.5 * iqr, q3 + 1.5 * iqr)
    for tid, v in usable.items():
        flagged = [
            metric
            for metric, (lo, hi) in bounds.items()
            if isinstance(v.get(metric), (int, float)) and not lo <= v[metric] <= hi
        ]
        if len(flagged) >= 2:
            # id, never pdf_filename: Category.IDENTIFYING must not reach a
            # written file (ADR-0016 rev. 2 "Privacy", Sec. 9.8.3)
            data.notable.append((f"thesis {tid}", flagged))
    return data


# -- chart statistics (was matplotlib's) --------------------------------------


@dataclass(frozen=True)
class BoxStats:
    """Five-number summary plus fliers, matplotlib's boxplot convention."""

    q1: float
    median: float
    q3: float
    whisker_lo: float
    whisker_hi: float
    fliers: tuple[float, ...]


def box_stats(values) -> BoxStats | None:
    """Quartiles, 1.5 x IQR whiskers and fliers for one box (Sec. 9.8.3).

    Same convention as the grid's outlier highlighting and as
    ``matplotlib.cbook.boxplot_stats``: Q1/Q3 by linear interpolation
    (``statistics.quantiles(..., method="inclusive")``), fences at
    1.5 x IQR, and whiskers drawn to the most extreme datum still inside
    the fence rather than to the fence itself."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        only = ordered[0]
        return BoxStats(only, only, only, only, only, ())
    q1, median, q3 = statistics.quantiles(ordered, n=4, method="inclusive")
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = [v for v in ordered if lo_fence <= v <= hi_fence]
    return BoxStats(
        q1,
        median,
        q3,
        inside[0] if inside else ordered[0],
        inside[-1] if inside else ordered[-1],
        tuple(v for v in ordered if not lo_fence <= v <= hi_fence),
    )


def histogram(
    values, bins: int = 15, span: tuple[float, float] | None = None
) -> tuple[list[float], list[int]]:
    """Equal-width bin edges and counts (Sec. 9.8.3).

    ``numpy.histogram``'s convention: ``bins`` equal-width bins over
    ``span`` (default the data's own [min, max]), each half-open except
    the last, which is closed on both ends. An all-equal series widens to
    [x - 0.5, x + 0.5], as numpy does. ``span`` lets several series share
    one binning so overlaid histograms line up."""
    data = [float(v) for v in values]
    if bins < 1 or (not data and span is None):
        return [], []
    lo, hi = span if span is not None else (min(data), max(data))
    lo, hi = float(min(lo, hi)), float(max(lo, hi))
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    width = (hi - lo) / bins
    edges = [lo + i * width for i in range(bins + 1)]
    edges[-1] = hi
    counts = [0] * bins
    for value in data:
        index = min(int((value - lo) / width), bins - 1)
        # float division can land a value one bin off its edge; walk it back
        while index > 0 and value < edges[index]:
            index -= 1
        while index < bins - 1 and value >= edges[index + 1]:
            index += 1
        if 0 <= index < bins:
            counts[index] += 1
    return edges, counts


# -- SVG plotting -------------------------------------------------------------

PLOT_W, PLOT_H = 520, 320
M_LEFT, M_RIGHT, M_TOP, M_BOTTOM = 66, 18, 16, 46

HIST_BINS = 15
#: Categorical hues are assigned in fixed order and never cycled. Three is
#: the validated all-pairs cap for scatter/overlay forms; the tail folds into
#: one neutral "other" series instead of inventing a fourth hue.
MAX_SERIES = 3


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _fmt(value: float) -> str:
    """Axis-tick / table formatting: integers stay integers, and only as
    many decimals as the magnitude needs."""
    if value == int(value):
        whole = int(value)
        return f"{whole:,}" if abs(whole) >= 10000 else str(whole)
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 1:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _fmt_year(value: float) -> str:
    return str(int(round(value)))


def _nice_step(span: float, target: int, min_step: float | None) -> float:
    raw = span / max(target, 1)
    if raw <= 0:
        raw = 1.0
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = 10.0 * magnitude
    for factor in (1.0, 2.0, 2.5, 5.0):
        if factor * magnitude >= raw:
            step = factor * magnitude
            break
    if min_step is not None and step < min_step:
        step = min_step
    return step


def _axis_ticks(lo, hi, target: int = 5, min_step: float | None = None) -> list[float]:
    """Round tick values whose first and last bound the axis (linear only)."""
    lo, hi = float(min(lo, hi)), float(max(lo, hi))
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    step = _nice_step(hi - lo, target, min_step)
    first = math.floor(lo / step) * step
    count = max(1, int(math.ceil((hi - first) / step - 1e-9)))
    return [round(first + i * step, 10) for i in range(count + 1)]


def _series_class(index: int) -> str:
    return f"s{index + 1}" if index < MAX_SERIES else "sx"


def _fold_series(ordered: list[tuple[str, list]]) -> list[tuple[str, list]]:
    """Merge everything past ``MAX_SERIES`` into one neutral series."""
    head, tail = ordered[:MAX_SERIES], ordered[MAX_SERIES:]
    if not tail:
        return head
    merged: list = []
    for _, series in tail:
        merged.extend(series)
    return head + [(f"other ({len(tail)} more)", merged)]


class _Plot:
    """A minimal linear-axis SVG frame: hairline grid, round ticks, no deps.

    Either ``x_ticks`` (numeric x) or ``categories`` (banded x) is given.
    Marks are appended to ``body`` in user coordinates via ``x``/``y``.
    """

    def __init__(
        self,
        y_ticks: list[float],
        *,
        x_ticks: list[float] | None = None,
        categories: list[str] | None = None,
        x_label: str = "",
        y_label: str = "",
        x_fmt=_fmt,
        y_fmt=_fmt,
    ) -> None:
        self.px0, self.px1 = float(M_LEFT), float(PLOT_W - M_RIGHT)
        self.py0, self.py1 = float(PLOT_H - M_BOTTOM), float(M_TOP)  # y grows upward
        self.y_lo, self.y_hi = y_ticks[0], y_ticks[-1]
        self.x_lo, self.x_hi = (x_ticks[0], x_ticks[-1]) if x_ticks else (0.0, 1.0)
        self.categories = list(categories or [])
        self.body: list[str] = []
        frame: list[str] = []
        for value in y_ticks:
            py = self.y(value)
            frame.append(
                f'<line class="grid" x1="{self.px0:.1f}" y1="{py:.1f}"'
                f' x2="{self.px1:.1f}" y2="{py:.1f}"/>'
            )
            frame.append(
                f'<text class="tick ty" x="{self.px0 - 9:.1f}" y="{py + 4:.1f}">'
                f"{_esc(y_fmt(value))}</text>"
            )
        for value in x_ticks or []:
            px = self.x(value)
            frame.append(
                f'<line class="grid" x1="{px:.1f}" y1="{self.py0:.1f}"'
                f' x2="{px:.1f}" y2="{self.py0 + 5:.1f}"/>'
            )
            frame.append(
                f'<text class="tick tx" x="{px:.1f}" y="{self.py0 + 19:.1f}">'
                f"{_esc(x_fmt(value))}</text>"
            )
        for index, name in enumerate(self.categories):
            frame.append(
                f'<text class="tick tx" x="{self.band(index):.1f}"'
                f' y="{self.py0 + 19:.1f}">{_esc(name)}</text>'
            )
        frame.append(
            f'<line class="axis" x1="{self.px0:.1f}" y1="{self.py0:.1f}"'
            f' x2="{self.px1:.1f}" y2="{self.py0:.1f}"/>'
        )
        frame.append(
            f'<line class="axis" x1="{self.px0:.1f}" y1="{self.py0:.1f}"'
            f' x2="{self.px0:.1f}" y2="{self.py1:.1f}"/>'
        )
        if x_label:
            mid = (self.px0 + self.px1) / 2
            frame.append(
                f'<text class="axlabel tx" x="{mid:.1f}" y="{PLOT_H - 8}">'
                f"{_esc(x_label)}</text>"
            )
        if y_label:
            mid = (self.py0 + self.py1) / 2
            frame.append(
                f'<text class="axlabel tx" x="14" y="{mid:.1f}"'
                f' transform="rotate(-90 14 {mid:.1f})">{_esc(y_label)}</text>'
            )
        self.frame = frame

    def x(self, value: float) -> float:
        if self.x_hi == self.x_lo:
            return (self.px0 + self.px1) / 2
        ratio = (value - self.x_lo) / (self.x_hi - self.x_lo)
        return self.px0 + ratio * (self.px1 - self.px0)

    def y(self, value: float) -> float:
        if self.y_hi == self.y_lo:
            return (self.py0 + self.py1) / 2
        ratio = (value - self.y_lo) / (self.y_hi - self.y_lo)
        return self.py0 + ratio * (self.py1 - self.py0)

    def band_width(self) -> float:
        return (self.px1 - self.px0) / max(len(self.categories), 1)

    def band(self, index: int) -> float:
        return self.px0 + (index + 0.5) * self.band_width()

    def render(self, description: str) -> str:
        return (
            f'<svg viewBox="0 0 {PLOT_W} {PLOT_H}" role="img"'
            f' preserveAspectRatio="xMidYMid meet"><title>{_esc(description)}</title>'
            + "".join(self.frame)
            + "".join(self.body)
            + "</svg>"
        )


def _legend(entries: list[tuple[str, str]]) -> str:
    """Identity is never colour-alone: a legend for every multi-series chart."""
    if len(entries) < 2:
        return ""
    items = "".join(
        f'<li><span class="swatch {cls}"></span>{_esc(label)}</li>' for label, cls in entries
    )
    return f'<ul class="legend">{items}</ul>'


def _table(headers: list[str], rows: list[list[str]], summary: str = "Data table") -> str:
    """The chart's numbers, collapsed. Carries identity for readers who
    cannot separate the hues, and discharges the palette's contrast relief."""
    if not rows:
        return ""
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        f"<details class=\"data\"><summary>{_esc(summary)}</summary>"
        f"<div class=\"scroll\"><table><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div></details>"
    )


def _panel(title: str, *parts: str) -> str:
    return (
        f'<section class="panel"><h3>{_esc(title)}</h3>'
        + "".join(p for p in parts if p)
        + "</section>"
    )


def _empty(message: str) -> str:
    return f'<p class="empty">{_esc(message)}</p>'


# -- the four charts ----------------------------------------------------------


def _chart_length_over_time(data: ReportData) -> str:
    points = data.words_by_year
    if not points:
        return _empty("No thesis has both a word count and a publication year yet.")
    grouped: dict[str, list[tuple[int, float]]] = {}
    for year, word_count, thesis_type in points:
        grouped.setdefault(thesis_type, []).append((year, word_count))
    series = _fold_series(sorted(grouped.items()))
    years = [y for y, _, _ in points]
    words = [w for _, w, _ in points]

    trend = None
    lows, highs = [0.0, min(words)], [max(words)]
    if len(points) >= 5:  # trend line only with >= 5 points (Sec. 9.8.3)
        slope, intercept = statistics.linear_regression(years, words)
        x0, x1 = min(years), max(years)
        trend = ((x0, slope * x0 + intercept), (x1, slope * x1 + intercept))
        lows += [trend[0][1], trend[1][1]]
        highs += [trend[0][1], trend[1][1]]

    plot = _Plot(
        _axis_ticks(min(lows), max(highs)),
        x_ticks=_axis_ticks(min(years), max(years), min_step=1.0),
        x_label="publication year",
        y_label="words",
        x_fmt=_fmt_year,
    )
    for index, (label, pairs) in enumerate(series):
        cls = _series_class(index)
        for year, word_count in sorted(pairs):
            plot.body.append(
                f'<circle class="dot {cls}" cx="{plot.x(year):.1f}"'
                f' cy="{plot.y(word_count):.1f}" r="4.5"><title>'
                f"{_esc(label)}: {_fmt(word_count)} words, {_fmt_year(year)}"
                "</title></circle>"
            )
    if trend is not None:
        (x0, y0), (x1, y1) = trend
        plot.body.append(
            f'<line class="trend" x1="{plot.x(x0):.1f}" y1="{plot.y(y0):.1f}"'
            f' x2="{plot.x(x1):.1f}" y2="{plot.y(y1):.1f}"><title>'
            "linear trend</title></line>"
        )
    rows = [
        [_fmt_year(year), thesis_type, _fmt(word_count)]
        for year, word_count, thesis_type in sorted(points)
    ]
    caption = (
        '<p class="note">Dashed line: least-squares trend over all plotted theses.</p>'
        if trend is not None
        else '<p class="note">Trend line needs at least 5 dated theses.</p>'
    )
    return (
        plot.render("Scatter plot of thesis word count against publication year.")
        + _legend([(label, _series_class(i)) for i, (label, _) in enumerate(series)])
        + caption
        + _table(["publication year", "type", "words"], rows)
    )


def _chart_length_by_type(data: ReportData) -> str:
    present = [(name, values) for name, values in sorted(data.words_by_type.items()) if values]
    if not present:
        return _empty("No word counts recorded yet.")
    boxes = [(name, box_stats(values), values) for name, values in present]
    spread = [
        value
        for _, box, _ in boxes
        for value in (box.whisker_lo, box.whisker_hi, *box.fliers)
    ]
    plot = _Plot(
        _axis_ticks(min(spread), max(spread)),
        categories=[name for name, _, _ in boxes],
        y_label="words",
    )
    width = min(plot.band_width() * 0.46, 84.0)
    for index, (name, box, values) in enumerate(boxes):
        cx = plot.band(index)
        left, top = cx - width / 2, plot.y(box.q3)
        height = max(abs(plot.y(box.q1) - plot.y(box.q3)), 1.0)
        tip = (
            f"{name}: n={len(values)}, median {_fmt(box.median)}, "
            f"Q1 {_fmt(box.q1)}, Q3 {_fmt(box.q3)}"
        )
        plot.body.append(
            f'<line class="whisker" x1="{cx:.1f}" y1="{plot.y(box.whisker_lo):.1f}"'
            f' x2="{cx:.1f}" y2="{plot.y(box.whisker_hi):.1f}"/>'
        )
        for value in (box.whisker_lo, box.whisker_hi):
            plot.body.append(
                f'<line class="whisker" x1="{cx - width / 4:.1f}"'
                f' y1="{plot.y(value):.1f}" x2="{cx + width / 4:.1f}"'
                f' y2="{plot.y(value):.1f}"/>'
            )
        plot.body.append(
            f'<rect class="box s1" x="{left:.1f}" y="{top:.1f}" width="{width:.1f}"'
            f' height="{height:.1f}" rx="3"><title>{_esc(tip)}</title></rect>'
        )
        plot.body.append(
            f'<line class="median" x1="{left:.1f}" y1="{plot.y(box.median):.1f}"'
            f' x2="{left + width:.1f}" y2="{plot.y(box.median):.1f}"/>'
        )
        for value in box.fliers:
            plot.body.append(
                f'<circle class="flier" cx="{cx:.1f}" cy="{plot.y(value):.1f}" r="4">'
                f"<title>{_esc(name)} outlier: {_fmt(value)} words</title></circle>"
            )
    rows = [
        [
            name,
            str(len(values)),
            _fmt(box.whisker_lo),
            _fmt(box.q1),
            _fmt(box.median),
            _fmt(box.q3),
            _fmt(box.whisker_hi),
            str(len(box.fliers)),
        ]
        for name, box, values in boxes
    ]
    return (
        plot.render("Box plots of thesis word count per detected thesis type.")
        + '<p class="note">Box: Q1 to Q3 with the median. Whiskers reach the most'
        " extreme thesis within 1.5 x IQR; points beyond are drawn separately.</p>"
        + _table(
            ["type", "n", "low whisker", "Q1", "median", "Q3", "high whisker", "outliers"],
            rows,
        )
    )


def _chart_reading_ease(data: ReportData) -> str:
    present = [(lang, values) for lang, values in data.fre_by_language.items() if values]
    if not present:
        return _empty("No reading-ease scores recorded yet.")
    # biggest samples keep the fixed categorical hues; the tail folds to one
    present.sort(key=lambda item: (-len(item[1]), item[0]))
    series = _fold_series(present)
    everything = [value for _, values in series for value in values]
    edges, _ = histogram(everything, bins=HIST_BINS)
    span = (edges[0], edges[-1])
    binned = [(label, histogram(values, bins=HIST_BINS, span=span)[1]) for label, values in series]
    peak = max((count for _, counts in binned for count in counts), default=1)

    plot = _Plot(
        _axis_ticks(0, peak, min_step=1.0),
        x_ticks=_axis_ticks(span[0], span[1]),
        x_label="Flesch reading ease",
        y_label="theses",
    )
    for index, (label, counts) in enumerate(binned):
        cls = _series_class(index)
        for slot, count in enumerate(counts):
            if not count:
                continue
            left, right = plot.x(edges[slot]), plot.x(edges[slot + 1])
            top = plot.y(count)
            tip = (
                f"{label}: {count} thesis(es) between "
                f"{_fmt(edges[slot])} and {_fmt(edges[slot + 1])}"
            )
            plot.body.append(
                f'<rect class="hbar {cls}" x="{left + 1:.1f}" y="{top:.1f}"'
                f' width="{max(right - left - 2, 1.0):.1f}"'
                f' height="{max(plot.y(0) - top, 1.0):.1f}" rx="2">'
                f"<title>{_esc(tip)}</title></rect>"
            )
    rows = [
        [f"{_fmt(edges[slot])} to {_fmt(edges[slot + 1])}"]
        + [str(counts[slot]) for _, counts in binned]
        for slot in range(HIST_BINS)
        if any(counts[slot] for _, counts in binned)
    ]
    return (
        plot.render("Histogram of Flesch reading-ease scores, one series per language.")
        + _legend([(label, _series_class(i)) for i, (label, _) in enumerate(binned)])
        + f'<p class="note">{HIST_BINS} equal-width bins; series are overlaid, not'
        " stacked.</p>"
        + _table(["reading ease"] + [label for label, _ in binned], rows)
    )


def _chart_language_mix(data: ReportData) -> str:
    items = sorted(data.by_language.items())
    if not items:
        return _empty("No language has been detected yet.")
    plot = _Plot(
        _axis_ticks(0, max(count for _, count in items), min_step=1.0),
        categories=[lang for lang, _ in items],
        y_label="theses",
    )
    width = min(plot.band_width() * 0.55, 78.0)
    baseline = plot.y(0)
    for index, (lang, count) in enumerate(items):
        cx = plot.band(index)
        top = plot.y(count)
        plot.body.append(
            f'<rect class="bar s1" x="{cx - width / 2:.1f}" y="{top:.1f}"'
            f' width="{width:.1f}" height="{max(baseline - top, 1.0):.1f}" rx="4">'
            f"<title>{_esc(lang)}: {count} thesis(es)</title></rect>"
        )
        plot.body.append(
            f'<text class="value tx" x="{cx:.1f}" y="{top - 7:.1f}">{count}</text>'
        )
    return (
        plot.render("Bar chart of thesis counts per detected language.")
        + _table(["language", "theses"], [[lang, str(count)] for lang, count in items])
    )


# -- the document -------------------------------------------------------------

_STYLE = """
:root {
  color-scheme: light;
  --surface: #fcfcfb; --card: #ffffff; --line: #e4e3df; --grid: #eceae5;
  --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #7a7975;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-x: #7a7f87;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --surface: #1a1a19; --card: #232322; --line: #35342f; --grid: #2c2b28;
    --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #9b9a92;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-x: #8d9199;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 20px 56px; background: var(--surface); color: var(--ink);
  font: 15px/1.55 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
main { max-width: 1060px; margin: 0 auto; }
h1 { font-size: 25px; letter-spacing: -0.01em; margin: 0 0 4px; }
h2 { font-size: 15px; font-weight: 600; text-transform: uppercase;
     letter-spacing: 0.07em; color: var(--ink-3); margin: 40px 0 12px; }
h3 { font-size: 15px; font-weight: 600; margin: 0 0 10px; }
.sub { color: var(--ink-2); margin: 0 0 4px; }
.cards { display: grid; gap: 12px; margin-top: 16px;
         grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 12px 14px; }
.card dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
           color: var(--ink-3); margin: 0 0 4px; }
.card dd { margin: 0; font-size: 21px; font-weight: 600; letter-spacing: -0.01em; }
.card dd small { display: block; font-size: 12px; font-weight: 400; color: var(--ink-2);
                 letter-spacing: 0; }
.grid2 { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
         padding: 16px; }
.panel svg { display: block; width: 100%; height: auto; overflow: visible; }
.note, .caption { color: var(--ink-3); font-size: 12.5px; margin: 8px 0 0; }
.empty { color: var(--ink-3); font-size: 13.5px; margin: 0; padding: 28px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; list-style: none;
          margin: 10px 0 0; padding: 0; font-size: 13px; color: var(--ink-2); }
.legend li { display: flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; background: var(--series); }
.s1 { --series: var(--series-1); }
.s2 { --series: var(--series-2); }
.s3 { --series: var(--series-3); }
.sx { --series: var(--series-x); }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--line); stroke-width: 1; }
.tick { fill: var(--ink-3); font-size: 11px; }
.ty { text-anchor: end; }
.tx { text-anchor: middle; }
.axlabel { fill: var(--ink-2); font-size: 12px; }
.value { fill: var(--ink-2); font-size: 11px; }
.dot { fill: var(--series); stroke: var(--card); stroke-width: 2; }
.bar, .box, .hbar { fill: var(--series); }
.hbar { fill-opacity: 0.62; }
.trend { stroke: var(--ink-3); stroke-width: 2; stroke-dasharray: 6 4; }
.whisker { stroke: var(--ink-2); stroke-width: 1.5; }
.median { stroke: var(--card); stroke-width: 2.5; }
.flier { fill: none; stroke: var(--ink-2); stroke-width: 1.5; }
details.data { margin-top: 12px; }
details.data summary { cursor: pointer; font-size: 12.5px; color: var(--ink-3); }
.scroll { overflow-x: auto; margin-top: 8px; }
table { border-collapse: collapse; font-size: 13px; width: 100%; }
th, td { text-align: left; padding: 5px 12px 5px 0; border-bottom: 1px solid var(--line);
         white-space: nowrap; }
th { color: var(--ink-3); font-weight: 600; }
table.notable { max-width: 640px; }
footer { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line);
         color: var(--ink-3); font-size: 12.5px; }
@media print {
  body { padding: 0; background: #ffffff; }
  .grid2 { grid-template-columns: 1fr; }
  .panel { break-inside: avoid; border-color: #cccccc; }
  details.data { display: none; }
}
"""


def _card(term: str, value: str, note: str = "") -> str:
    detail = f"<small>{_esc(note)}</small>" if note else ""
    return f"<div class=\"card\"><dt>{_esc(term)}</dt><dd>{_esc(value)}{detail}</dd></div>"


def _summary_cards(data: ReportData) -> str:
    languages = " ".join(f"{k}={n}" for k, n in sorted(data.by_language.items())) or "-"
    years = f"{data.year_range[0]}-{data.year_range[1]}" if data.year_range else "-"
    types = " | ".join(f"{k}: {n}" for k, n in sorted(data.by_type.items())) or "no type detected"
    median = f"{data.median_words:,.0f}" if data.median_words is not None else "-"
    return (
        '<dl class="cards">'
        + _card("Theses analysed", str(data.theses), types)
        + _card("Excluded", str(data.excluded), "left out of every aggregate")
        + _card("Languages", languages)
        + _card("Publication years", years)
        + _card("Median length", median, "words")
        + "</dl>"
    )


def _notable_section(data: ReportData) -> str:
    if not data.notable:
        return _empty(
            "No thesis is an outlier on two or more of the trustworthy metrics "
            f"({', '.join(TRUSTWORTHY_METRICS)})."
        )
    head = "<thead><tr><th>Thesis</th><th>Outlier on</th></tr></thead>"
    body = "".join(
        f"<tr><td>{_esc(label)}</td><td>{_esc(', '.join(metrics))}</td></tr>"
        for label, metrics in data.notable
    )
    return (
        f'<div class="scroll"><table class="notable">{head}<tbody>{body}</tbody></table></div>'
        '<p class="note">Flagged by per-metric IQR (1.5 x IQR beyond Q1/Q3) on at least'
        " two of avg_word_len, std_sentence_len, yules_k, flesch_reading_ease. Theses are"
        " named by id - no file name leaves the database (Sec. 9.8.3); <code>tta list</code>"
        " resolves an id.</p>"
    )


def render_html(data: ReportData, generated_at: datetime | None = None) -> str:
    """One self-contained HTML document, as a string (Sec. 9.8).

    All CSS and all SVG are inline and the document makes no external
    request whatsoever - no script, no image, no web font, no CDN
    (QA-PRIV). It contains no identifying value (Sec. 9.8.3)."""
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    garbled = (
        f'<p class="caption">{data.garbled} thesis(es) with a garbled text extraction'
        " are excluded from every aggregate above and below.</p>"
        if data.garbled
        else ""
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Thesis Text Analyzer - cohort report {_esc(stamp)}</title>"
        f"<style>{_STYLE}</style></head><body><main>"
        "<h1>Cohort report</h1>"
        f'<p class="sub">Thesis Text Analyzer - {data.theses} analysed'
        f" thesis(es), generated {_esc(stamp)}</p>"
        + _summary_cards(data)
        + garbled
        + "<h2>Trends</h2><div class=\"grid2\">"
        + _panel("Length over time", _chart_length_over_time(data))
        + _panel("Length by type", _chart_length_by_type(data))
        + "</div><h2>Distributions</h2><div class=\"grid2\">"
        + _panel("Reading ease distribution", _chart_reading_ease(data))
        + _panel("Language mix", _chart_language_mix(data))
        + "</div><h2>Notable theses</h2>"
        + f'<section class="panel">{_notable_section(data)}</section>'
        + "<footer>Generated locally by tta "
        + _esc(tta.__version__)
        + ". This file is self-contained: it loads nothing from the network and"
        " contains no file names, paths, notes or document text. Regenerate it any"
        " time from the Report button or <code>tta report</code>.</footer>"
        "</main></body></html>\n"
    )
