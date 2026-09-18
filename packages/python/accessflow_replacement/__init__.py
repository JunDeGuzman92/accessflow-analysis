"""Topology-based replacement-path evidence for candidate graph edges."""

from .aggregate import RestrictionImpact, aggregate_restriction
from .replacement import EdgeReplacement, evaluate_edge
from .set_impact import RestrictionSetImpact, evaluate_edge_set

__all__ = ["EdgeReplacement", "RestrictionImpact", "RestrictionSetImpact", "aggregate_restriction", "evaluate_edge", "evaluate_edge_set"]