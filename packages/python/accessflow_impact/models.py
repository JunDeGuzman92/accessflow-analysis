"""Typed input and output contracts for Phase 13 assessments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ImpactSeverity(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class EvidenceConfidence(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class AssessmentInput:
    """Metrics for one restriction; unavailable metrics remain ``None``."""

    restriction_id: str
    valid_restriction_polyline: bool
    candidate_edge_count: int
    high_confidence_match_count: int
    medium_confidence_match_count: int
    low_confidence_match_count: int
    direct_intersection_count: int
    proximity_only_count: int
    affected_edge_length_m: float | None = None
    baseline_distance_m: float | None = None
    disrupted_distance_m: float | None = None
    added_distance_m: float | None = None
    detour_ratio: float | None = None
    connectivity_lost: bool | None = None
    removed_edge_count: int | None = None
    penalized_edge_count: int | None = None
    fallback_geometry_used: bool = False
    duration_hours: float | None = None
    missing_fields: tuple[str, ...] = ()
    topology_limitations: tuple[str, ...] = (
        "CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE",
        "CANDIDATE_SEGMENTS_ARE_NOT_CONFIRMED_CLOSURES",
    )


@dataclass(frozen=True)
class AssessmentResult:
    restriction_id: str
    impact_severity: ImpactSeverity
    evidence_confidence: EvidenceConfidence
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    explanation: str