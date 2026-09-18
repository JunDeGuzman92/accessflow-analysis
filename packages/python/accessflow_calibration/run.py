"""Build the Phase 14 evidence cohort CSV from immutable Phase 9 inputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from packages.python.accessflow_impact import AssessmentInput, assess
from packages.python.accessflow_spatial.matching import (
    load_network_segments,
    match_restrictions,
    parse_restrictions,
    transform_geometries,
)

from .cohort import CohortCandidate, select_cohort
from .dataset import AnalyticalRecord, write_csv


def _duration_hours(record: ET.Element) -> float | None:
    values = {child.tag: (child.text or "").strip() for child in record}
    try:
        start = datetime.fromtimestamp(float(values["StartTime"]) / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(float(values["EndTime"]) / 1000, tz=timezone.utc)
    except (KeyError, ValueError, OSError, OverflowError):
        return None
    return (end - start).total_seconds() / 3600 if end >= start else None


def build_cohort(raw_dir: Path, output: Path) -> list[AnalyticalRecord]:
    """Replay 5 m matching and write spatial-evidence records with no inferred routing."""
    road_path = next(raw_dir.glob("road-restrictions--resource-*.xml"))
    network_path = next(raw_dir.glob("pedestrian-network--resource-*.gpkg"))
    restrictions = parse_restrictions(road_path)
    segments = load_network_segments(network_path)
    matches = match_restrictions(restrictions, segments, thresholds_metres=(5.0,))
    projected = transform_geometries([segment.geometry_wgs84 for segment in segments])
    segment_lengths = {segment.segment_id: float(geometry.length) for segment, geometry in zip(segments, projected)}
    temporal = {
        (record.findtext("Id") or "").strip(): _duration_hours(record)
        for record in ET.parse(road_path).getroot()
    }
    points = {item.restriction_id: item for item in restrictions}
    selected_input: list[CohortCandidate] = []
    for result in matches:
        candidates = result.candidates
        direct = sum(item.signal == "direct_intersection" for item in candidates)
        proximity = sum(item.signal == "proximity" for item in candidates)
        fallback = sum(item.signal == "point_fallback" for item in candidates)
        group = "FALLBACK" if result.malformed_polyline else "DIRECT" if direct else "PROXIMITY_ONLY" if proximity else "NO_CANDIDATE"
        point = points[result.restriction_id].point_wgs84
        selected_input.append(CohortCandidate(result.restriction_id, group, len(candidates), point.x, point.y))
    chosen = {item.restriction_id for item in select_cohort(selected_input)}
    manifests = sorted((raw_dir / "manifests").glob("*.json"))
    snapshot = ";".join(json.loads(path.read_text(encoding="utf-8"))["sha256"] for path in manifests if "pedestrian-network" in path.name or "road-restrictions" in path.name)
    records: list[AnalyticalRecord] = []
    for result in matches:
        if result.restriction_id not in chosen:
            continue
        candidates = result.candidates
        direct = sum(item.signal == "direct_intersection" for item in candidates)
        proximity = sum(item.signal == "proximity" for item in candidates)
        fallback = sum(item.signal == "point_fallback" for item in candidates)
        inputs = AssessmentInput(
            restriction_id=result.restriction_id,
            valid_restriction_polyline=not result.malformed_polyline,
            candidate_edge_count=len(candidates),
            high_confidence_match_count=direct,
            medium_confidence_match_count=proximity,
            low_confidence_match_count=fallback,
            direct_intersection_count=direct,
            proximity_only_count=proximity,
            affected_edge_length_m=sum(segment_lengths[item.segment_id] for item in candidates),
            fallback_geometry_used=result.malformed_polyline,
            duration_hours=temporal[result.restriction_id],
            missing_fields=("ENDTIME",) if temporal[result.restriction_id] is None else (),
        )
        assessment = assess(inputs)
        records.append(AnalyticalRecord(
            restriction_id=result.restriction_id, evaluation_status="SPATIAL_EVIDENCE_ONLY",
            valid_restriction_polyline=not result.malformed_polyline, fallback_geometry_used=result.malformed_polyline,
            candidate_edge_count=len(candidates), direct_intersection_count=direct, proximity_only_count=proximity,
            high_confidence_match_count=direct, medium_confidence_match_count=proximity, low_confidence_match_count=fallback,
            affected_edge_length_m=inputs.affected_edge_length_m, evidence_confidence=assessment.evidence_confidence.value,
            network_evaluated=False, baseline_distance_m=None, disrupted_distance_m=None, added_distance_m=None,
            detour_ratio=None, connectivity_lost=None, removed_edge_count=None, penalized_edge_count=None,
            impact_severity=assessment.impact_severity.value, reason_codes=";".join(assessment.reason_codes),
            limitations=";".join(assessment.limitation_codes), impact_evaluable=False,
            duration_hours=inputs.duration_hours, source_snapshot=snapshot,
            quality_flags="MALFORMED_POLYLINE" if result.malformed_polyline else "",
        ))
    write_csv(output, records)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/phase14-evaluation-cohort.csv"))
    arguments = parser.parse_args()
    print(json.dumps({"record_count": len(build_cohort(arguments.raw_dir, arguments.output)), "output": str(arguments.output)}))


if __name__ == "__main__":
    main()