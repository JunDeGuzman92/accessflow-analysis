"""Analytical CSV records with explicit unavailable network fields."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalyticalRecord:
    restriction_id: str
    evaluation_status: str
    valid_restriction_polyline: bool
    fallback_geometry_used: bool
    candidate_edge_count: int
    direct_intersection_count: int
    proximity_only_count: int
    high_confidence_match_count: int
    medium_confidence_match_count: int
    low_confidence_match_count: int
    affected_edge_length_m: float | None
    evidence_confidence: str
    network_evaluated: bool
    baseline_distance_m: float | None
    disrupted_distance_m: float | None
    added_distance_m: float | None
    detour_ratio: float | None
    connectivity_lost: bool | None
    removed_edge_count: int | None
    penalized_edge_count: int | None
    impact_severity: str
    reason_codes: str
    limitations: str
    impact_evaluable: bool
    duration_hours: float | None
    source_snapshot: str
    quality_flags: str


def write_csv(path: Path, records: list[AnalyticalRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(AnalyticalRecord.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)