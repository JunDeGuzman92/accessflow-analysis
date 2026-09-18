"""Distribution summaries that preserve missing values as missing."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Iterable


@dataclass(frozen=True)
class DistributionSummary:
    count: int
    missing_count: int
    minimum: float | None
    median: float | None
    mean: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    maximum: float | None


def summarize(values: Iterable[float | None]) -> DistributionSummary:
    supplied = tuple(values)
    observed = sorted(float(value) for value in supplied if value is not None)
    total = len(supplied)
    if not observed:
        return DistributionSummary(0, total, None, None, None, None, None, None, None, None, None, None)

    def percentile(percent: float) -> float:
        index = (len(observed) - 1) * percent
        lower, upper = math.floor(index), math.ceil(index)
        return observed[lower] if lower == upper else observed[lower] + (observed[upper] - observed[lower]) * (index - lower)

    return DistributionSummary(
        len(observed), total - len(observed), observed[0], median(observed), mean(observed),
        percentile(.25), percentile(.50), percentile(.75), percentile(.90), percentile(.95), percentile(.99), observed[-1],
    )