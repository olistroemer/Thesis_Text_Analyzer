"""Grid column model (SDD §9.2/§9.3): lead columns + metric columns
derived from the module catalogue; basic mode shows a curated subset."""

from __future__ import annotations

from dataclasses import dataclass

from pds.core.modules.registry import ModuleRegistry

LEAD_COLUMNS = ("file", "type")

#: Curated basic-mode metric subset (§9.3 "limited columns visible by default").
BASIC_METRICS = (
    "n_pages",
    "language_code",
    "word_count",
    "flesch_reading_ease",
    "yules_k",
    "extraction_quality",
)


@dataclass(frozen=True)
class MetricColumn:
    metric: str
    module: str


def metric_columns(registry: ModuleRegistry, extended: bool) -> list[MetricColumn]:
    columns = [
        MetricColumn(metric=metric, module=module.spec.name)
        for module in registry.in_topological_order()
        for metric in module.spec.produces_metrics
    ]
    if extended:
        return columns
    by_name = {c.metric: c for c in columns}
    return [by_name[m] for m in BASIC_METRICS if m in by_name]
