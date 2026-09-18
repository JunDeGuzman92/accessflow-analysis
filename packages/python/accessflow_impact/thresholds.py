"""Readable Phase 13 severity-rule configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeverityThresholds:
    """Deterministic rules for evaluated, connected hard-closure experiments."""

    high_added_distance_m: float
    high_detour_ratio: float


# Phase 12 has two measurable hard-closure detours: 64.803 m / 7.395x and
# 193.559 m / 6.572x. The midpoint separates them without using extremes.
PHASE12_MIDPOINT = SeverityThresholds(
    high_added_distance_m=129.181,
    high_detour_ratio=6.983,
)

# A comparison scheme uses upper-half observed values rather than midpoints.
PHASE12_UPPER_QUARTILE = SeverityThresholds(
    high_added_distance_m=161.370,
    high_detour_ratio=7.189,
)