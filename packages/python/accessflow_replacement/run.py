"""Run bounded Phase 15 replacement-path evaluation for the Phase 14 cohort."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

from packages.python.accessflow_calibration.cohort import CohortCandidate, select_cohort
from packages.python.accessflow_graph.network import build_graph
from packages.python.accessflow_spatial.matching import load_network_segments, match_restrictions, parse_restrictions

from .aggregate import aggregate_restriction
from .replacement import evaluate_edge
from .set_impact import evaluate_edge_set


MAX_SET_EDGES = 2


def _write(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({field for record in records for field in record})
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def _cohort_ids(restrictions, matches) -> set[str]:
    inputs = []
    points = {item.restriction_id: item.point_wgs84 for item in restrictions}
    for result in matches:
        direct = sum(item.signal == "direct_intersection" for item in result.candidates)
        proximity = sum(item.signal == "proximity" for item in result.candidates)
        group = "FALLBACK" if result.malformed_polyline else "DIRECT" if direct else "PROXIMITY_ONLY" if proximity else "NO_CANDIDATE"
        point = points[result.restriction_id]
        inputs.append(CohortCandidate(result.restriction_id, group, len(result.candidates), point.x, point.y))
    return {item.restriction_id for item in select_cohort(inputs)}


def run(raw_dir: Path, edge_output: Path, restriction_output: Path) -> tuple[int, int]:
    """Evaluate local replacement paths for both documented evidence scenarios."""
    road_path = next(raw_dir.glob("road-restrictions--resource-*.xml"))
    network_path = next(raw_dir.glob("pedestrian-network--resource-*.gpkg"))
    restrictions = parse_restrictions(road_path)
    segments = load_network_segments(network_path)
    matches = match_restrictions(restrictions, segments, thresholds_metres=(5.0,))
    cohort_ids = _cohort_ids(restrictions, matches)
    build = build_graph(segments, endpoint_tolerance_m=.001)
    graph_edges = {edge.source_segment_id: edge for edge in build.edges}
    edge_rows: list[dict[str, object]] = []
    restriction_rows: list[dict[str, object]] = []
    for result in matches:
        if result.restriction_id not in cohort_ids:
            continue
        for scenario, allowed in (("HIGH_ONLY", {"HIGH"}), ("HIGH_MEDIUM", {"HIGH", "MEDIUM"})):
            candidates = [item for item in result.candidates if item.confidence in allowed]
            evaluated = [
                evaluate_edge(build, graph_edges[item.segment_id], restriction_id=result.restriction_id, match_type=item.signal, evidence_confidence=item.confidence)
                for item in candidates if item.segment_id in graph_edges
            ]
            for item in evaluated:
                row = asdict(item)
                row["scenario"] = scenario
                row["limitations"] = ";".join(item.limitations)
                edge_rows.append(row)
            set_result = evaluate_edge_set(build, result.restriction_id, [graph_edges[item.segment_id] for item in candidates if item.segment_id in graph_edges]) if len(evaluated) <= MAX_SET_EDGES else None
            aggregate = aggregate_restriction(evaluated, set_result)
            row = asdict(aggregate)
            row.update({
                "scenario": scenario,
                "source_candidate_count": len(result.candidates),
                "excluded_low_confidence_count": sum(item.confidence == "LOW" for item in result.candidates),
                "set_evaluation_state": set_result.evaluation_state if set_result else "NOT_EVALUATED",
                "set_evaluation_reason": "EDGE_SET_EXCEEDS_BOUND" if set_result is None else "",
            })
            restriction_rows.append(row)
    _write(edge_output, edge_rows)
    _write(restriction_output, restriction_rows)
    return len(edge_rows), len(restriction_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--edge-output", type=Path, default=Path("data/processed/phase15-edge-replacement.csv"))
    parser.add_argument("--restriction-output", type=Path, default=Path("data/processed/phase15-restriction-impact.csv"))
    args = parser.parse_args()
    edges, restrictions = run(args.raw_dir, args.edge_output, args.restriction_output)
    print(json.dumps({"edge_record_count": edges, "restriction_record_count": restrictions}))


if __name__ == "__main__":
    main()