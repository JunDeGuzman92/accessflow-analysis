"""Framework-independent service models backed by reproducible artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RestrictionSummary:
    restriction_id: str
    evaluation_status: str
    impact_severity: str
    evidence_confidence: str
    candidate_edge_count: int
    impact_evaluable: bool
    source_snapshot: str
    match_type: str | None
    duration_hours: float | None


@dataclass(frozen=True)
class RestrictionDetail(RestrictionSummary):
    valid_restriction_polyline: bool
    fallback_geometry_used: bool
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    restriction_geometry: dict[str, Any] | None


@dataclass(frozen=True)
class CandidateMatch:
    restriction_id: str
    pedestrian_feature_id: str
    match_type: str
    evidence_confidence: str
    distance_m: float | None
    candidate_status: str
    geometry: dict[str, Any] | None
    source: str | None = None
    candidate_rank: int | None = None


@dataclass(frozen=True)
class NetworkImpact:
    restriction_id: str
    scenario: str
    evaluation_status: str
    candidate_edge_count: int
    evaluated_edge_count: int
    alternative_path_edge_count: int
    local_connectivity_loss_count: int
    local_connectivity_loss_fraction: float | None
    median_replacement_ratio: float | None
    max_replacement_ratio: float | None
    median_added_replacement_distance_m: float | None
    max_added_replacement_distance_m: float | None
    set_evaluation_status: str
    set_component_increase: int | None
    set_disconnected_boundary_pair_count: int | None
    limitations: tuple[str, ...]