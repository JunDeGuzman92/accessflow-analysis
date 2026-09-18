"""Deterministic persistence for verified Phase 11 spatial evidence."""

from __future__ import annotations

import json
import hashlib
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from shapely.geometry import mapping

from .matching import NetworkSegment, RestrictionMatchSummary, RestrictionRecord, SOURCE_CRS

ARTIFACT_SCHEMA_VERSION = "phase22-spatial-v1"


def _finite_pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)


def valid_geojson(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("type") not in {"Point", "LineString", "MultiLineString"}:
        return None
    coordinates = value.get("coordinates")
    geometry_type = value["type"]
    if geometry_type == "Point" and _finite_pair(coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    if geometry_type == "LineString" and isinstance(coordinates, list) and len(coordinates) >= 2 and all(_finite_pair(item) for item in coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    if geometry_type == "MultiLineString" and isinstance(coordinates, list) and coordinates and all(isinstance(line, list) and len(line) >= 2 and all(_finite_pair(item) for item in line) for line in coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    return None


def _geometry(value: object | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        if value.is_empty or not value.is_valid:
            return None
        return valid_geojson(json.loads(json.dumps(mapping(value))))
    except (AttributeError, TypeError, ValueError):
        return None


def build_spatial_artifact(
    restrictions: Iterable[RestrictionRecord],
    segments: Iterable[NetworkSegment],
    matches: Iterable[RestrictionMatchSummary],
    *,
    source_snapshot: str | None = None,
    source_artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build JSON-safe evidence without repairing or deriving geometry."""
    segment_map = {segment.segment_id: segment for segment in segments}
    match_map = {result.restriction_id: result for result in matches}
    records: dict[str, Any] = {}
    candidate_count = 0
    candidate_geometry_count = 0
    restriction_geometry_count = 0
    rejected_geometry_count = 0
    available_count = 0
    partial_count = 0
    not_available_count = 0
    for restriction in restrictions:
        result = match_map.get(restriction.restriction_id)
        candidate_rows = [] if result is None else result.candidates
        features = []
        restriction_geometry = _geometry(restriction.line_wgs84)
        if restriction_geometry is not None:
            restriction_geometry_count += 1
        elif restriction.malformed_polyline:
            rejected_geometry_count += 1
        for rank, candidate in enumerate(candidate_rows, start=1):
            segment = segment_map.get(candidate.segment_id)
            candidate_geometry = _geometry(segment.geometry_wgs84) if segment is not None else None
            candidate_count += 1
            if candidate_geometry is not None:
                candidate_geometry_count += 1
            elif segment is not None:
                rejected_geometry_count += 1
            features.append({
                "feature_id": candidate.segment_id,
                "geometry": candidate_geometry,
                "match_type": candidate.signal,
                "confidence": candidate.confidence,
                "distance_m": None if candidate.threshold_metres is None and candidate.signal == "direct_intersection" else candidate.distance_metres,
                "source": "phase11-network-segment-artifact" if segment is not None else None,
                "candidate_rank": rank,
                "candidate_status": "CANDIDATE_AFFECTED_SEGMENT",
            })
        geometry_values = [restriction_geometry] + [feature["geometry"] for feature in features]
        available_geometry = sum(value is not None for value in geometry_values)
        if available_geometry == 0:
            geometry_status = "NOT_AVAILABLE"
            not_available_count += 1
        elif available_geometry == len(geometry_values):
            geometry_status = "AVAILABLE"
            available_count += 1
        else:
            geometry_status = "PARTIAL"
            partial_count += 1
        records[restriction.restriction_id] = {
            "restriction_geometry": restriction_geometry,
            "restriction_source_id": restriction.restriction_id,
            "matches": features,
            "geometry_status": geometry_status,
            "geometry_provenance": {
                "restriction_source": "phase11-restriction-geopolyline",
                "network_source": "phase11-network-segment-artifact",
                "source_snapshot": source_snapshot,
                "crs": SOURCE_CRS,
            },
        }
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "crs": SOURCE_CRS,
        "source_snapshot": source_snapshot,
        "source_artifacts": source_artifacts or {},
        "integrity": {
            "restriction_record_count": len(records),
            "candidate_feature_count": candidate_count,
            "restriction_geometry_available_count": restriction_geometry_count,
            "candidate_geometry_available_count": candidate_geometry_count,
            "rejected_geometry_count": rejected_geometry_count,
            "available_restriction_count": available_count,
            "partial_restriction_count": partial_count,
            "not_available_restriction_count": not_available_count,
            "null_geometry_count": (len(records) + candidate_count) - restriction_geometry_count - candidate_geometry_count,
        },
        "records": records,
    }


def build_spatial_artifact_from_phase11(
    restriction_path: Path,
    network_path: Path,
    matches: Iterable[RestrictionMatchSummary],
    *,
    source_snapshot: str | None = None,
) -> dict[str, Any]:
    """Load Phase 11 source geometry and persist already-computed match evidence."""
    from .matching import load_network_segments, parse_restrictions

    return build_spatial_artifact(
        parse_restrictions(restriction_path),
        load_network_segments(network_path),
        matches,
        source_snapshot=source_snapshot,
    )


def write_spatial_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_artifact(artifact: dict[str, Any]) -> str:
    payload = json.dumps(artifact, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_spatial_artifact(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        artifact = json.load(source)
    if not isinstance(artifact, dict) or artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("Invalid spatial artifact schema version")
    if artifact.get("crs") != SOURCE_CRS or not isinstance(artifact.get("source_snapshot"), str) or not artifact["source_snapshot"]:
        raise ValueError("Invalid spatial artifact CRS or provenance")
    if not isinstance(artifact.get("source_artifacts"), dict) or not isinstance(artifact.get("integrity"), dict) or not isinstance(artifact.get("records"), dict):
        raise ValueError("Invalid spatial artifact structure")
    required_integrity = {"restriction_record_count", "candidate_feature_count", "restriction_geometry_available_count", "candidate_geometry_available_count", "rejected_geometry_count", "available_restriction_count", "partial_restriction_count", "not_available_restriction_count", "null_geometry_count"}
    if not required_integrity.issubset(artifact["integrity"]):
        raise ValueError("Incomplete spatial artifact integrity metadata")
    for restriction_id, record in artifact["records"].items():
        if not isinstance(restriction_id, str) or not isinstance(record, dict) or record.get("restriction_source_id") != restriction_id:
            raise ValueError("Invalid spatial artifact restriction identity")
        if record.get("geometry_status") not in {"AVAILABLE", "PARTIAL", "NOT_AVAILABLE"}:
            raise ValueError("Invalid spatial artifact geometry status")
        if not isinstance(record.get("geometry_provenance"), dict) or record["geometry_provenance"].get("crs") != SOURCE_CRS:
            raise ValueError("Missing spatial geometry provenance")
        for geometry in [record.get("restriction_geometry")]:
            if geometry is not None and valid_geojson(geometry) is None:
                raise ValueError("Malformed spatial artifact geometry")
        features = record.get("matches")
        if not isinstance(features, list):
            raise ValueError("Invalid spatial artifact matches")
        feature_ids = set()
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("feature_id"), str) or feature["feature_id"] in feature_ids:
                raise ValueError("Duplicate or invalid spatial feature identifier")
            feature_ids.add(feature["feature_id"])
            if feature.get("geometry") is not None and valid_geojson(feature["geometry"]) is None:
                raise ValueError("Malformed spatial feature geometry")
    return artifact
