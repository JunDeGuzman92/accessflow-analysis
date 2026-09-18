"""Artifact-backed repository boundary; HTTP handlers never run spatial analysis."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

from .models import CandidateMatch, NetworkImpact, RestrictionDetail, RestrictionSummary
from packages.python.accessflow_spatial.artifacts import load_spatial_artifact


class ArtifactUnavailableError(RuntimeError):
    """Raised when a required reproducible analytical artifact is absent."""


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured persistence backend cannot be reached or initialized."""


class AccessFlowRepository(Protocol):
    def list_restrictions(self, *, offset: int, limit: int, evaluation_status: str | None, impact_severity: str | None, evidence_confidence: str | None) -> tuple[list[RestrictionSummary], int]: ...
    def get_restriction(self, restriction_id: str) -> RestrictionDetail | None: ...
    def get_matches(self, restriction_id: str) -> list[CandidateMatch] | None: ...
    def get_spatial_artifact(self, restriction_id: str) -> dict[str, object] | None: ...
    def get_network_impact(self, restriction_id: str) -> list[NetworkImpact] | None: ...
    def analytics_summary(self) -> dict[str, object]: ...


def _number(value: str | None) -> float | None:
    return float(value) if value not in {None, ""} else None


def _integer(value: str | None) -> int | None:
    return int(float(value)) if value not in {None, ""} else None


def _boolean(value: str | None) -> bool:
    return value == "True"


def _codes(value: str | None) -> tuple[str, ...]:
    return tuple(item for item in (value or "").split(";") if item)


class CsvAccessFlowRepository:
    """Read precomputed Phase 14/15 CSVs once; no routing executes during requests."""

    def __init__(self, data_dir: Path) -> None:
        cohort = data_dir / "phase14-evaluation-cohort.csv"
        edges = data_dir / "phase15-edge-replacement.csv"
        impacts = data_dir / "phase15-restriction-impact.csv"
        self._spatial = load_spatial_artifact(data_dir / "phase22-spatial.json") if (data_dir / "phase22-spatial.json").exists() else {"records": {}}
        missing = [path.name for path in (cohort, edges, impacts) if not path.exists()]
        if missing:
            raise ArtifactUnavailableError("Required analytical artifacts are unavailable")
        with cohort.open(encoding="utf-8", newline="") as source:
            self._restrictions = {row["restriction_id"]: row for row in csv.DictReader(source)}
        with edges.open(encoding="utf-8", newline="") as source:
            self._edges = list(csv.DictReader(source))
        with impacts.open(encoding="utf-8", newline="") as source:
            self._impacts = list(csv.DictReader(source))

    def _summary(self, row: dict[str, str]) -> RestrictionSummary:
        return RestrictionSummary(row["restriction_id"], row["evaluation_status"], row["impact_severity"], row["evidence_confidence"], int(row["candidate_edge_count"]), _boolean(row["impact_evaluable"]), row["source_snapshot"])

    def list_restrictions(self, *, offset: int, limit: int, evaluation_status: str | None, impact_severity: str | None, evidence_confidence: str | None) -> tuple[list[RestrictionSummary], int]:
        records = [self._summary(row) for row in self._restrictions.values()]
        records = [item for item in records if (evaluation_status is None or item.evaluation_status == evaluation_status) and (impact_severity is None or item.impact_severity == impact_severity) and (evidence_confidence is None or item.evidence_confidence == evidence_confidence)]
        records.sort(key=lambda item: item.restriction_id)
        return records[offset:offset + limit], len(records)

    def get_restriction(self, restriction_id: str) -> RestrictionDetail | None:
        row = self._restrictions.get(restriction_id)
        if row is None:
            return None
        summary = self._summary(row)
        spatial = self._spatial["records"].get(restriction_id, {})
        return RestrictionDetail(**summary.__dict__, valid_restriction_polyline=_boolean(row["valid_restriction_polyline"]), fallback_geometry_used=_boolean(row["fallback_geometry_used"]), duration_hours=_number(row["duration_hours"]), reason_codes=_codes(row["reason_codes"]), limitations=_codes(row["limitations"]), restriction_geometry=spatial.get("restriction_geometry"))

    def get_matches(self, restriction_id: str) -> list[CandidateMatch] | None:
        if restriction_id not in self._restrictions:
            return None
        seen: dict[str, CandidateMatch] = {}
        for row in self._edges:
            if row["restriction_id"] != restriction_id:
                continue
            spatial_matches = self._spatial["records"].get(restriction_id, {}).get("matches", [])
            spatial_match = next((item for item in spatial_matches if item.get("feature_id") == row["source_segment_id"]), {})
            candidate = CandidateMatch(restriction_id, row["source_segment_id"], row["match_type"], row["evidence_confidence"], _number(row.get("distance_m")), "CANDIDATE_AFFECTED_SEGMENT", spatial_match.get("geometry"), spatial_match.get("source"), spatial_match.get("candidate_rank"))
            seen.setdefault(candidate.pedestrian_feature_id, candidate)
        return sorted(seen.values(), key=lambda item: item.pedestrian_feature_id)

    def get_spatial_artifact(self, restriction_id: str) -> dict[str, object] | None:
        if restriction_id not in self._restrictions:
            return None
        return self._spatial["records"].get(restriction_id, {})

    def get_network_impact(self, restriction_id: str) -> list[NetworkImpact] | None:
        if restriction_id not in self._restrictions:
            return None
        output = []
        for row in self._impacts:
            if row["restriction_id"] != restriction_id:
                continue
            output.append(NetworkImpact(
                restriction_id, row["scenario"], row["evaluation_state"], int(float(row["candidate_edge_count"])), int(float(row["evaluated_edge_count"])), int(float(row["alternative_path_edge_count"])), int(float(row["local_connectivity_loss_count"])), _number(row["local_connectivity_loss_fraction"]), _number(row["median_replacement_ratio"]), _number(row["max_replacement_ratio"]), _number(row["median_added_replacement_distance_m"]), _number(row["max_added_replacement_distance_m"]), row["set_evaluation_state"], _integer(row["restriction_set_component_increase"]), _integer(row["restriction_set_disconnected_boundary_pair_count"]), ("GEOMETRY_DERIVED_CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE", "CANDIDATE_SEGMENTS_ARE_NOT_CONFIRMED_CLOSURES"),
            ))
        return output

    def analytics_summary(self) -> dict[str, object]:
        records = [self._summary(row) for row in self._restrictions.values()]
        def counts(values: list[str]) -> dict[str, int]:
            return {value: values.count(value) for value in sorted(set(values))}
        return {"total_restrictions_represented": len(records), "evaluation_status_distribution": counts([item.evaluation_status for item in records]), "impact_severity_distribution": counts([item.impact_severity for item in records]), "evidence_confidence_distribution": counts([item.evidence_confidence for item in records]), "evaluated_restrictions": sum(item.impact_evaluable for item in records)}