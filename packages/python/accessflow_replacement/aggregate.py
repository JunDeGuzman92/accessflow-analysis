"""Transparent restriction-level summaries over evaluated edge effects."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .replacement import EdgeReplacement
from .set_impact import RestrictionSetImpact


@dataclass(frozen=True)
class RestrictionImpact:
    restriction_id: str
    evaluation_state: str
    candidate_edge_count: int
    evaluated_edge_count: int
    alternative_path_edge_count: int
    local_connectivity_loss_count: int
    local_connectivity_loss_fraction: float | None
    median_replacement_ratio: float | None
    max_replacement_ratio: float | None
    p90_replacement_ratio: float | None
    median_added_replacement_distance_m: float | None
    max_added_replacement_distance_m: float | None
    affected_edge_length_m: float
    restriction_set_component_increase: int | None
    restriction_set_disconnected_boundary_pair_count: int | None


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values.sort()
    index = (len(values) - 1) * quantile
    lower, upper = int(index), min(int(index) + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def aggregate_restriction(edges: list[EdgeReplacement], set_impact: RestrictionSetImpact | None = None) -> RestrictionImpact:
    """Aggregate only evaluated values; unavailable replacements remain ``None``."""
    restriction_id = edges[0].restriction_id if edges else (set_impact.restriction_id if set_impact else "")
    evaluated = [edge for edge in edges if edge.evaluation_state == "EVALUATED"]
    ratios = [edge.replacement_ratio for edge in evaluated if edge.replacement_ratio is not None]
    added = [edge.added_replacement_distance_m for edge in evaluated if edge.added_replacement_distance_m is not None]
    losses = sum(edge.local_connectivity_lost is True for edge in evaluated)
    state = "INSUFFICIENT_EVIDENCE" if not edges else "EVALUATED" if len(evaluated) == len(edges) else "PARTIALLY_EVALUATED"
    return RestrictionImpact(
        restriction_id, state, len(edges), len(evaluated), len(ratios), losses,
        losses / len(evaluated) if evaluated else None,
        median(ratios) if ratios else None, max(ratios) if ratios else None, _percentile(ratios, .9),
        median(added) if added else None, max(added) if added else None,
        sum(edge.original_edge_length_m for edge in edges),
        set_impact.component_increase if set_impact else None,
        set_impact.disconnected_boundary_pair_count if set_impact else None,
    )