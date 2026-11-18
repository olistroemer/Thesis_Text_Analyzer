"""Reference aggregates shipped inside the app (ADR-0025, SDD Sec. 9.8).

The professor report compares the professor's theses with the research
team's reference corpus. Only six statistics per bucket and metric travel
(mean, median, 5th/25th/75th/95th percentile), never a count and never an
individual reference value. Each statistic has its own minimum number of
theses (``min_theses``): the centre and the quartiles need fewer than the
5th/95th percentiles, which on a short series are little more than its
minimum and maximum. This module holds both halves that must agree:

* the **report side**: ``load_shipped()`` reads the packaged JSON,
  ``Reference.stats()`` looks a bucket up, ``band_level()`` says how far
  outside the reference bands a value lies;
* the **generator's pure half**: the population rule
  (``reference_split``), the metric catalogue and its derived metrics
  (``derive_metrics``), the bucket statistics (``build_aggregates``) and the
  file format (``dump_aggregates``). The harvest-specific half lives in
  ``tools/reference_aggregates.py`` and is never frozen.

Stdlib only (``statistics``, ``json``), no I/O except reading the packaged
file through ``importlib.resources``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from importlib import resources

from tta.core.i18n import N_
from tta.core.types import REFERENCE_THESIS_TYPES

FORMAT = "tta-reference-aggregates"
#: 2: one threshold per statistic; p05/p95 may be null (ADR-0025 rev. 2).
FORMAT_VERSION = 2

#: Publication years the reference covers (ADR-0025 decision 3).
YEARS = (2003, 2025)

STATS = ("mean", "median", "p05", "p25", "p75", "p95")

#: A statistic ships only if at least this many theses have a value for the
#: metric in the bucket (ADR-0025 decision 5, rev. 2): the centre and the
#: inner band (mean, median, p25, p75) from 4, the outer band (p05, p95)
#: from 20.
MIN_THESES_INNER = 4
MIN_THESES_OUTER = 20
INNER_STATS = ("mean", "median", "p25", "p75")
OUTER_STATS = ("p05", "p95")

#: Languages with their own buckets; the yearly summary takes every language.
LANGUAGES = ("de", "en")

#: The bucket value meaning "every type / language / field".
ALL = "all"

#: DDC main classes - the reference's field (ADR-0025 decision 6).
DDC_MAIN_CLASSES: dict[str, str] = {
    "000": N_("000 Computer science, information, general works"),
    "100": N_("100 Philosophy and psychology"),
    "200": N_("200 Religion"),
    "300": N_("300 Social sciences"),
    "400": N_("400 Language"),
    "500": N_("500 Natural sciences and mathematics"),
    "600": N_("600 Technology, medicine, applied sciences"),
    "700": N_("700 Arts and recreation"),
    "800": N_("800 Literature"),
    "900": N_("900 History and geography"),
}
FIELDS = tuple(DDC_MAIN_CLASSES)

#: The report's metric catalogue, in its three panels (ADR-0025 decision 7).
METRIC_GROUPS: dict[str, tuple[str, ...]] = {
    "length": (
        "word_count",
        "n_pages",
        "char_count_alpha",
        "text_chars",
        "sentence_count",
        "n_images",
        "avg_sentence_len",
        "file_size_mb",
        "words_per_page",
        "images_per_page",
        "kb_per_page",
    ),
    "style": (
        "flesch_reading_ease",
        "yules_k",
        "avg_word_len",
        "std_sentence_len",
        "bigram_repetition_rate",
        "trigram_repetition_rate",
    ),
    "vocabulary": ("ttr", "root_ttr", "hapax_token_ratio", "hapax_type_ratio"),
}
METRICS = tuple(name for group in METRIC_GROUPS.values() for name in group)

#: Metrics computed from others by ``derive_metrics`` (both sides).
DERIVED = ("file_size_mb", "words_per_page", "images_per_page", "kb_per_page")

METRIC_LABELS: dict[str, str] = {
    "word_count": N_("words"),
    "n_pages": N_("pages"),
    "char_count_alpha": N_("letters"),
    "text_chars": N_("extracted characters"),
    "sentence_count": N_("sentences"),
    "n_images": N_("images"),
    "avg_sentence_len": N_("average sentence length (words)"),
    "file_size_mb": N_("file size (MB)"),
    "words_per_page": N_("words per page"),
    "images_per_page": N_("images per page"),
    "kb_per_page": N_("kB per page"),
    "flesch_reading_ease": N_("reading ease (Flesch / Amstad)"),
    "yules_k": N_("Yule's K"),
    "avg_word_len": N_("average word length (characters)"),
    "std_sentence_len": N_("sentence length spread (std. dev.)"),
    "bigram_repetition_rate": N_("bigram repetition rate"),
    "trigram_repetition_rate": N_("trigram repetition rate"),
    "ttr": N_("type-token ratio"),
    "root_ttr": N_("root TTR"),
    "hapax_token_ratio": N_("hapax share of tokens"),
    "hapax_type_ratio": N_("hapax share of types"),
}

#: Where the packaged data lives (``tta/core/report_assets/``).
ASSETS_PACKAGE = "tta.core"
ASSETS_DIR = "report_assets"
AGGREGATES_FILENAME = "reference_aggregates.json"


def _number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def derive_metrics(values: dict) -> dict[str, float]:
    """The catalogue's metrics of one thesis, derived ones included.

    ``values`` is one thesis's current metrics (name -> value). The one
    derivation both the generator and the report use, so a reference band
    and a professor's point are always the same quantity."""
    out = {name: float(values[name]) for name in METRICS if _number(values.get(name))}
    size = values.get("file_size_bytes")
    pages = values.get("n_pages")
    if _number(size):
        out["file_size_mb"] = size / 1_000_000.0
    if _number(pages) and pages > 0:
        if _number(values.get("word_count")):
            out["words_per_page"] = values["word_count"] / pages
        if _number(values.get("n_images")):
            out["images_per_page"] = values["n_images"] / pages
        if _number(size):
            out["kb_per_page"] = size / 1000.0 / pages
    return out


def year_in_range(year) -> bool:
    return _number(year) and YEARS[0] <= int(year) <= YEARS[1]


def reference_split(values: dict) -> tuple[str, str | None, int] | None:
    """(type, language or None, year) of a thesis that enters the reference,
    else None (ADR-0025 decision 4). All three are the app's detected
    metrics. The language is None unless it has its own buckets; such a
    thesis still counts in the yearly summary."""
    thesis_type = values.get("thesis_type")
    year = values.get("publication_year")
    if thesis_type not in REFERENCE_THESIS_TYPES or not year_in_range(year):
        return None
    language = values.get("language_code")
    return thesis_type, (language if language in LANGUAGES else None), int(year)


def quantile(ordered: list[float], fraction: float) -> float:
    """Linear interpolation between the closest ranks - numpy's default and
    ``statistics.quantiles(..., method="inclusive")``. ``ordered`` is sorted."""
    if not ordered:
        raise ValueError("quantile of an empty series")
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _round(value: float) -> float:
    """4 significant digits: precise enough for a band, short in the file."""
    return float(f"{value:.4g}")


def min_theses(min_inner: int = MIN_THESES_INNER,
               min_outer: int = MIN_THESES_OUTER) -> dict[str, int]:
    """The threshold of every statistic, in ``STATS`` order."""
    return {stat: (min_outer if stat in OUTER_STATS else min_inner) for stat in STATS}


def summarise(values: list[float], *, outer: bool = True) -> list[float | None]:
    """The six statistics, in ``STATS`` order, rounded. Without ``outer``,
    p05 and p95 are None (too few theses for the outer band)."""
    ordered = sorted(values)
    return [
        _round(math.fsum(ordered) / len(ordered)),
        _round(quantile(ordered, 0.5)),
        _round(quantile(ordered, 0.05)) if outer else None,
        _round(quantile(ordered, 0.25)),
        _round(quantile(ordered, 0.75)),
        _round(quantile(ordered, 0.95)) if outer else None,
    ]


@dataclass
class ReferenceThesis:
    """One reference thesis as the generator sees it."""

    thesis_type: str
    language: str | None
    field: str | None  # a DDC main class, or None for an unknown field
    year: int
    metrics: dict[str, float] = field(default_factory=dict)


def bucket_keys(thesis: ReferenceThesis) -> list[tuple[str, str, str, int]]:
    """Every bucket one thesis counts in (ADR-0025 decisions 3 and 5)."""
    keys = [(ALL, ALL, ALL, thesis.year)]
    if thesis.language is not None:
        keys.append((thesis.thesis_type, thesis.language, ALL, thesis.year))
        if thesis.field in FIELDS:
            keys.append((thesis.thesis_type, thesis.language, thesis.field, thesis.year))
    return keys


def _sort_key(key: tuple[str, str, str, int]):
    thesis_type, language, field_code, year = key
    return (year, thesis_type != ALL, thesis_type, language, field_code != ALL, field_code)


def build_aggregates(
    theses,
    *,
    status: str,
    source: str,
    generated: str,
    generator: str,
    analysed_with: list[str] | tuple[str, ...] = (),
    min_inner: int = MIN_THESES_INNER,
    min_outer: int = MIN_THESES_OUTER,
) -> dict:
    """The shipped document from individual reference theses.

    Every bucket is computed directly from the theses, so a thesis of a
    dropped small bucket still counts in the coarser ones. A metric ships
    with mean, median, p25 and p75 from ``min_inner`` values and also with
    p05 and p95 from ``min_outer`` (else those two are None); a bucket with
    no metric is not shipped. No count of any kind enters the result."""
    if status not in ("interim", "release"):
        raise ValueError(f"status must be interim or release, not {status!r}")
    if not 1 <= min_inner <= min_outer:
        raise ValueError("thresholds must satisfy 1 <= min_inner <= min_outer")
    buckets: dict[tuple, dict[str, list[float]]] = {}
    for thesis in theses:
        for key in bucket_keys(thesis):
            series = buckets.setdefault(key, {})
            for name, value in thesis.metrics.items():
                if name in METRICS:
                    series.setdefault(name, []).append(value)
    rows = []
    for key in sorted(buckets, key=_sort_key):
        series = buckets[key]
        values = {
            name: summarise(series[name], outer=len(series[name]) >= min_outer)
            for name in METRICS
            if len(series.get(name, ())) >= min_inner
        }
        if values:
            thesis_type, language, field_code, year = key
            rows.append(
                {
                    "type": thesis_type,
                    "language": language,
                    "field": field_code,
                    "year": year,
                    "values": values,
                }
            )
    return {
        "_comment": (
            "Reference aggregates of the Thesis Text Analyzer (ADR-0025). Generated "
            "by tools/reference_aggregates.py - do not edit by hand. Six statistics "
            "per bucket and metric, no counts; a statistic ships only if at least "
            "min_theses[statistic] theses have a value, else it is null."
            + (
                " INTERIM: computed from an older analysis run, replaced before "
                "the release."
                if status == "interim"
                else ""
            )
        ),
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "status": status,
        "source": source,
        "generated": generated,
        "generator": generator,
        "analysed_with": list(analysed_with),
        "years": list(YEARS),
        "min_theses": min_theses(min_inner, min_outer),
        "stats": list(STATS),
        "metrics": list(METRICS),
        "fields": list(FIELDS),
        "rows": rows,
    }


def dump_aggregates(document: dict) -> str:
    """Deterministic JSON, one row per line, so a regeneration diffs well."""
    head = [
        f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=True)},"
        for key, value in document.items()
        if key != "rows"
    ]
    rows = [
        "    " + json.dumps(row, ensure_ascii=True, separators=(",", ":"))
        for row in document["rows"]
    ]
    return "{\n" + "\n".join(head) + '\n  "rows": [\n' + ",\n".join(rows) + "\n  ]\n}\n"


# -- the report side ----------------------------------------------------------


class Reference:
    """A validated aggregate document with bucket lookup."""

    def __init__(self, document: dict) -> None:
        if document.get("format") != FORMAT:
            raise ValueError("not a tta reference-aggregates document")
        if document.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"unsupported format_version {document.get('format_version')!r}")
        if tuple(document.get("stats", ())) != STATS:
            raise ValueError("unexpected statistics list")
        thresholds = document.get("min_theses")
        if (
            not isinstance(thresholds, dict)
            or tuple(thresholds) != STATS
            or not all(type(v) is int and v >= 1 for v in thresholds.values())
            or len({thresholds[s] for s in INNER_STATS}) != 1
            or len({thresholds[s] for s in OUTER_STATS}) != 1
            or thresholds["p05"] < thresholds["median"]
        ):
            raise ValueError("min_theses must give one threshold per statistic")
        self.document = document
        self.min_inner = thresholds["median"]
        self.min_outer = thresholds["p05"]
        self.status = document.get("status", "release")
        self.years = tuple(document.get("years", YEARS))
        self._rows: dict[tuple[str, str, str, int], dict[str, list[float]]] = {}
        for row in document.get("rows", ()):
            key = (row["type"], row["language"], row["field"], int(row["year"]))
            for values in row["values"].values():
                _check_values(values)
            self._rows[key] = row["values"]

    @property
    def fields(self) -> list[str]:
        """The fields that have at least one bucket, in DDC order."""
        present = {key[2] for key in self._rows}
        return [code for code in FIELDS if code in present]

    @property
    def rows(self) -> dict[tuple[str, str, str, int], dict[str, list[float]]]:
        return self._rows

    def stats(self, thesis_type: str, language: str, field_code: str, year: int,
              metric: str) -> dict[str, float | None] | None:
        """The bucket's statistics of one metric (p05/p95 None without an
        outer band), or None without a bucket or statistic."""
        values = self._rows.get((thesis_type, language, field_code, int(year)), {}).get(metric)
        return dict(zip(STATS, values)) if values else None


def _check_values(values) -> None:
    """Six entries in ``STATS`` order: the inner statistics always numbers,
    p05 and p95 both numbers or both null."""
    if not isinstance(values, list) or len(values) != len(STATS):
        raise ValueError("a metric needs one entry per statistic")
    stats = dict(zip(STATS, values))
    if not all(_number(stats[s]) for s in INNER_STATS):
        raise ValueError("mean, median, p25 and p75 must be numbers")
    outer = [stats[s] for s in OUTER_STATS]
    if not (all(v is None for v in outer) or all(_number(v) for v in outer)):
        raise ValueError("p05 and p95 must both be numbers or both be null")


def load_shipped() -> Reference | None:
    """The aggregates packaged with the app, or None when absent/unreadable
    (the report then renders without reference bands)."""
    try:
        resource = resources.files(ASSETS_PACKAGE) / ASSETS_DIR / AGGREGATES_FILENAME
        return Reference(json.loads(resource.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def band_level(value: float, stats: dict[str, float | None]) -> int:
    """How far outside the reference a value lies (SDD Sec. 9.8.3).

    0: inside [p25, p75]; 1: outside it but inside [p05, p95]; 2: outside
    [p05, p95]. Both edges of each band count as inside. Without an outer
    band (p05/p95 None) a value outside [p25, p75] is 1: nothing is claimed
    about a 5th-95th percentile the reference does not have."""
    if stats["p05"] is not None and (value < stats["p05"] or value > stats["p95"]):
        return 2
    if value < stats["p25"] or value > stats["p75"]:
        return 1
    return 0
