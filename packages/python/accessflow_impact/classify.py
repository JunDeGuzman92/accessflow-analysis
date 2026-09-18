"""Pure, explainable ordinal classification functions."""

from __future__ import annotations

from .explain import explain
from .models import AssessmentInput, AssessmentResult, EvidenceConfidence, ImpactSeverity
from .thresholds import PHASE12_MIDPOINT, SeverityThresholds


def _validate(metrics: AssessmentInput) -> None:
    if not metrics.restriction_id:
        raise ValueError("restriction_id is required")
    counts = (
        metrics.candidate_edge_count,
        metrics.high_confidence_match_count,
        metrics.medium_confidence_match_count,
        metrics.low_confidence_match_count,
        metrics.direct_intersection_count,
        metrics.proximity_only_count,
    )
    if any(value < 0 for value in counts):
        raise ValueError("match counts cannot be negative")
    for value in (
        metrics.affected_edge_length_m,
        metrics.baseline_distance_m,
        metrics.disrupted_distance_m,
        metrics.added_distance_m,
        metrics.detour_ratio,
        metrics.duration_hours,
    ):
        if value is not None and value < 0:
            raise ValueError("metric distances, ratios, and durations cannot be negative")


def _evidence_confidence(metrics: AssessmentInput) -> EvidenceConfidence:
    if metrics.candidate_edge_count == 0:
        return EvidenceConfidence.INSUFFICIENT_EVIDENCE
    if metrics.fallback_geometry_used or metrics.low_confidence_match_count:
        return EvidenceConfidence.LOW
    if metrics.direct_intersection_count and metrics.proximity_only_count == 0:
        return EvidenceConfidence.HIGH
    return EvidenceConfidence.MEDIUM


def assess(metrics: AssessmentInput, thresholds: SeverityThresholds = PHASE12_MIDPOINT) -> AssessmentResult:
    """Classify modeled impact independently from spatial-match confidence."""
    _validate(metrics)
    reasons: list[str] = []
    limitations = list(metrics.topology_limitations)
    evidence = _evidence_confidence(metrics)
    if metrics.candidate_edge_count == 0:
        reasons.append("NO_CANDIDATE_EDGE")
    if metrics.fallback_geometry_used:
        limitations.append("MATCH_BASED_ON_POINT_FALLBACK")
    elif metrics.proximity_only_count:
        limitations.append("MATCH_INCLUDES_PROXIMITY_CANDIDATES")
    if not metrics.valid_restriction_polyline:
        limitations.append("RESTRICTION_POLYLINE_MALFORMED")
    for field in metrics.missing_fields:
        limitations.append(f"MISSING_{field.upper()}")

    if metrics.candidate_edge_count == 0:
        severity = ImpactSeverity.NOT_EVALUATED
    elif metrics.connectivity_lost is True:
        severity = ImpactSeverity.SEVERE
        reasons.append("CONNECTIVITY_LOSS_MODELED")
    elif metrics.added_distance_m is None or metrics.detour_ratio is None:
        severity = ImpactSeverity.NOT_EVALUATED
        reasons.append("NETWORK_IMPACT_NOT_EVALUATED")
    elif metrics.added_distance_m == 0 and metrics.detour_ratio <= 1:
        severity = ImpactSeverity.LOW
        reasons.append("NO_MODELED_DETOUR")
    elif (
        metrics.added_distance_m >= thresholds.high_added_distance_m
        or metrics.detour_ratio >= thresholds.high_detour_ratio
    ):
        severity = ImpactSeverity.HIGH
        reasons.extend(("ADDED_DISTANCE_HIGH", "DETOUR_RATIO_HIGH"))
    else:
        severity = ImpactSeverity.MODERATE
        reasons.append("MODELED_DETOUR")

    result = AssessmentResult(
        restriction_id=metrics.restriction_id,
        impact_severity=severity,
        evidence_confidence=evidence,
        reason_codes=tuple(dict.fromkeys(reasons)),
        limitation_codes=tuple(dict.fromkeys(limitations)),
        explanation="",
    )
    return AssessmentResult(**{**result.__dict__, "explanation": explain(result)})