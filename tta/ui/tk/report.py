"""Report tab — the professor's reward (§9.8, ADR-0016, US-PROF-INSIGHTS).

Aggregates over `v_current_metrics` filtered to local, non-excluded
theses; garbled extractions are excluded from aggregates with a caption.
Linear axes throughout. matplotlib is imported lazily on first render.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from tkinter import ttk

from tta.core.db.repository import Repository

TRUSTWORTHY_METRICS = ("avg_word_len", "std_sentence_len", "yules_k", "flesch_reading_ease")


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
        thesis = included[tid]
        data.by_type[thesis.type] = data.by_type.get(thesis.type, 0) + 1
        language = v.get("language_code")
        if isinstance(language, str):
            data.by_language[language] = data.by_language.get(language, 0) + 1
        word_count = v.get("word_count")
        year = v.get("creation_year")
        if isinstance(word_count, (int, float)):
            words.append(word_count)
            data.words_by_type.setdefault(thesis.type, []).append(word_count)
            if isinstance(year, (int, float)):
                data.words_by_year.append((int(year), word_count, thesis.type))
                years.append(int(year))
        fre = v.get("flesch_reading_ease")
        if isinstance(fre, (int, float)) and isinstance(language, str):
            data.fre_by_language.setdefault(language, []).append(fre)
    if words:
        data.median_words = statistics.median(words)
    if years:
        data.year_range = (min(years), max(years))

    # notable theses: IQR outlier on ≥ 2 trustworthy metrics (§9.8.3)
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
            data.notable.append((included[tid].pdf_filename, flagged))
    return data


class ReportView(ttk.Frame):
    def __init__(self, parent, repo: Repository):
        super().__init__(parent)
        self.repo = repo
        self._canvas = None
        self.cards = ttk.Label(self, text="", justify="left", padding=8)
        self.cards.pack(anchor="w")
        self.chart_host = ttk.Frame(self)
        self.chart_host.pack(fill="both", expand=True)
        self.notable = ttk.Label(self, text="", justify="left", padding=8)
        self.notable.pack(anchor="w")

    def render(self) -> None:
        data = collect(self.repo)
        type_summary = " · ".join(f"{k}: {n}" for k, n in sorted(data.by_type.items()))
        language_summary = " ".join(f"{k}={n}" for k, n in sorted(data.by_language.items()))
        years = f"{data.year_range[0]}–{data.year_range[1]}" if data.year_range else "—"
        median = f"{data.median_words:.0f} words" if data.median_words is not None else "—"
        caption = f" · {data.garbled} garbled excluded from aggregates" if data.garbled else ""
        self.cards.configure(
            text=(
                f"{data.theses} theses analysed · {data.excluded} excluded · "
                f"Languages: {language_summary or '—'} · Years: {years}\n"
                f"{type_summary or 'no type attributes'} · Median length: {median}{caption}"
            )
        )
        self._draw_charts(data)
        if data.notable:
            lines = [
                f"• {name} · outlier on: {', '.join(metrics)}" for name, metrics in data.notable[:10]
            ]
            self.notable.configure(text="Notable theses\n" + "\n".join(lines))
        else:
            self.notable.configure(text="Notable theses: none flagged")

    def _draw_charts(self, data: ReportData) -> None:
        # lazy import: ~500 ms on first use (ADR-0016)
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
        figure = Figure(figsize=(9, 6), dpi=96, layout="constrained")
        axes = figure.subplots(2, 2)

        ax = axes[0][0]
        ax.set_title("Length over time")
        type_colors = {"bachelor": "tab:blue", "master": "tab:orange", "unspecified": "tab:gray"}
        for thesis_type in sorted({t for _, _, t in data.words_by_year} | set()):
            points = [(y, w) for y, w, t in data.words_by_year if t == thesis_type]
            ax.scatter(*zip(*points), label=thesis_type, color=type_colors.get(thesis_type))
        if len(data.words_by_year) >= 5:  # trend line only with ≥ 5 points (§9.8.3)
            xs = [y for y, _, _ in data.words_by_year]
            ys = [w for _, w, _ in data.words_by_year]
            slope, intercept = statistics.linear_regression(xs, ys)
            ax.plot(sorted(xs), [slope * x + intercept for x in sorted(xs)], "--", color="black")
        if data.words_by_year:
            ax.legend()
        ax.set_xlabel("year")
        ax.set_ylabel("words")

        ax = axes[0][1]
        ax.set_title("Length by type")
        present = [(k, v) for k, v in sorted(data.words_by_type.items()) if v]
        if present:
            ax.boxplot([v for _, v in present], tick_labels=[k for k, _ in present])
        ax.set_ylabel("words")

        ax = axes[1][0]
        ax.set_title("Reading ease distribution")
        for language, series in sorted(data.fre_by_language.items()):
            ax.hist(series, bins=15, alpha=0.6, label=language)
        if data.fre_by_language:
            ax.legend()
        ax.set_xlabel("Flesch reading ease")

        ax = axes[1][1]
        ax.set_title("Language mix")
        if data.by_language:
            ax.bar(list(data.by_language.keys()), list(data.by_language.values()))

        self._canvas = FigureCanvasTkAgg(figure, master=self.chart_host)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
