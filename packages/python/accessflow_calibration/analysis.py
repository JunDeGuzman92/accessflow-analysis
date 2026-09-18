"""Pure aggregate summaries for calibration artifacts."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from packages.python.accessflow_impact.profiling import summarize

from .dataset import AnalyticalRecord


def severity_distribution(records: Iterable[AnalyticalRecord]) -> dict[str, int]:
    return dict(sorted(Counter(record.impact_severity for record in records).items()))


def confidence_distribution(records: Iterable[AnalyticalRecord]) -> dict[str, int]:
    return dict(sorted(Counter(record.evidence_confidence for record in records).items()))


def severity_confidence_crosstab(records: Iterable[AnalyticalRecord]) -> dict[str, int]:
    return dict(sorted(Counter(f"{record.impact_severity}|{record.evidence_confidence}" for record in records).items()))


def metric_distributions(records: Iterable[AnalyticalRecord]) -> dict[str, object]:
    supplied = tuple(records)
    return {
        "candidate_edge_count": summarize(record.candidate_edge_count for record in supplied),
        "direct_intersection_count": summarize(record.direct_intersection_count for record in supplied),
        "affected_edge_length_m": summarize(record.affected_edge_length_m for record in supplied),
        "added_distance_m": summarize(record.added_distance_m for record in supplied),
        "detour_ratio": summarize(record.detour_ratio for record in supplied),
        "duration_hours": summarize(record.duration_hours for record in supplied),
    }