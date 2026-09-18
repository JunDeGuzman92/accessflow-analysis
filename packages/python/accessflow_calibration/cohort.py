"""Reproducible, evidence-stratified restriction cohort selection."""

from __future__ import annotations

from dataclasses import dataclass


DOWNTOWN_BOUNDS = (-79.41, -79.36, 43.63, 43.68)
PER_EVIDENCE_GEOGRAPHY_STRATUM = 12
NO_CANDIDATE_COUNT = 24


@dataclass(frozen=True)
class CohortCandidate:
    restriction_id: str
    evidence_group: str
    candidate_edge_count: int
    longitude: float
    latitude: float


def _downtown(candidate: CohortCandidate) -> bool:
    west, east, south, north = DOWNTOWN_BOUNDS
    return west <= candidate.longitude <= east and south <= candidate.latitude <= north


def _spread(items: list[CohortCandidate], count: int) -> list[CohortCandidate]:
    ordered = sorted(items, key=lambda item: (item.candidate_edge_count, item.restriction_id))
    if len(ordered) <= count:
        return ordered
    indices = {round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)}
    return [item for index, item in enumerate(ordered) if index in indices]


def select_cohort(candidates: list[CohortCandidate]) -> list[CohortCandidate]:
    """Select deterministic evidence/geography strata, retaining every fallback case."""
    selected: list[CohortCandidate] = []
    for evidence_group in ("DIRECT", "PROXIMITY_ONLY"):
        for downtown in (True, False):
            stratum = [
                item for item in candidates
                if item.evidence_group == evidence_group and _downtown(item) == downtown
            ]
            selected.extend(_spread(stratum, PER_EVIDENCE_GEOGRAPHY_STRATUM))
    selected.extend(sorted((item for item in candidates if item.evidence_group == "FALLBACK"), key=lambda item: item.restriction_id))
    selected.extend(sorted((item for item in candidates if item.evidence_group == "NO_CANDIDATE"), key=lambda item: item.restriction_id)[:NO_CANDIDATE_COUNT])
    return sorted({item.restriction_id: item for item in selected}.values(), key=lambda item: item.restriction_id)