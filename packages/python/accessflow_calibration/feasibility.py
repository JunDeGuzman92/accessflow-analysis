"""Conservative ML-target feasibility checks; no model training."""

from __future__ import annotations

from dataclasses import dataclass

from .dataset import AnalyticalRecord


@dataclass(frozen=True)
class TargetFeasibility:
    target: str
    usable_records: int
    class_counts: dict[str, int]
    verdict: str
    reasons: tuple[str, ...]


def assess_ml_target(records: list[AnalyticalRecord], target: str) -> TargetFeasibility:
    """Reject targets without evaluated labels or with direct simulation leakage."""
    evaluated = [record for record in records if record.impact_evaluable]
    labels = {record.impact_severity for record in evaluated}
    reasons: list[str] = []
    if not evaluated:
        reasons.append("NO_EVALUATED_NETWORK_LABELS")
    if target in {"added_distance_m", "detour_ratio", "connectivity_lost"}:
        reasons.append("TARGET_IS_POST_SIMULATION_OUTCOME")
    if target in {"high_severe", "severity_class"}:
        reasons.append("TARGET_IS_DERIVED_FROM_POST_SIMULATION_RULE_INPUTS")
    if len(labels) < 2:
        reasons.append("INSUFFICIENT_CLASS_VARIATION")
    counts = {label: sum(record.impact_severity == label for record in evaluated) for label in sorted(labels)}
    return TargetFeasibility(target, len(evaluated), counts, "ML_NOT_YET_JUSTIFIED", tuple(reasons))