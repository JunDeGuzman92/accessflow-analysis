"""Generate the deterministic Phase 22 spatial artifact from persisted evidence."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .artifacts import build_spatial_artifact, sha256_file, write_spatial_artifact
from .matching import MatchCandidate, RestrictionMatchSummary, load_network_segments, parse_restrictions


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restriction-source", type=Path, default=Path("data/raw/road-restrictions--resource-3afea38a-baad-4f39-b22f-d608875e1746.xml"))
    parser.add_argument("--network-source", type=Path, default=Path("data/raw/pedestrian-network--resource-f5390504-c209-42d5-aebe-c79a7a9267bc.gpkg"))
    parser.add_argument("--cohort", type=Path, default=Path("data/processed/phase14-evaluation-cohort.csv"))
    parser.add_argument("--matches", type=Path, default=Path("data/processed/phase15-edge-replacement.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/phase22-spatial.json"))
    return parser.parse_args()


def _match_summaries(path: Path, restriction_ids: set[str]) -> list[RestrictionMatchSummary]:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    grouped: dict[str, list[dict[str, str]]] = {restriction_id: [] for restriction_id in restriction_ids}
    for row in rows:
        if row["restriction_id"] in grouped:
            grouped[row["restriction_id"]].append(row)
    summaries = []
    for restriction_id in sorted(restriction_ids):
        candidates = []
        unique_rows = {}
        for row in sorted(grouped[restriction_id], key=lambda item: (item["source_segment_id"], item["match_type"], item.get("edge_id", ""), item.get("scenario", ""))):
            unique_rows.setdefault(row["source_segment_id"], row)
        for row in unique_rows.values():
            candidates.append(MatchCandidate(
                restriction_id=restriction_id,
                segment_id=row["source_segment_id"],
                signal=row["match_type"],
                threshold_metres=None,
                distance_metres=0.0 if row["match_type"] == "direct_intersection" else None,
                confidence=row["evidence_confidence"],
                fallback=row["match_type"] == "point_fallback",
            ))
        direct = tuple(sorted(candidate.segment_id for candidate in candidates if candidate.signal == "direct_intersection"))
        proximity = tuple(sorted(candidate.segment_id for candidate in candidates if candidate.signal == "proximity"))
        fallback = tuple(sorted(candidate.segment_id for candidate in candidates if candidate.signal == "point_fallback"))
        summaries.append(RestrictionMatchSummary(restriction_id, bool(fallback), "", "", "", "", not bool(fallback), direct, {5.0: proximity}, {5.0: fallback}, tuple(candidates)))
    return summaries


def main() -> int:
    args = _arguments()
    required = [args.restriction_source, args.network_source, args.cohort, args.matches]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"Missing required source artifacts: {', '.join(missing)}")
    cohort_rows = list(csv.DictReader(args.cohort.open(encoding="utf-8", newline="")))
    restriction_ids = {row["restriction_id"] for row in cohort_rows}
    restrictions = [item for item in parse_restrictions(args.restriction_source) if item.restriction_id in restriction_ids]
    segments = load_network_segments(args.network_source)
    matches = _match_summaries(args.matches, restriction_ids)
    source_artifacts = {path.as_posix(): {"sha256": sha256_file(path), "bytes": path.stat().st_size} for path in required}
    source_snapshot = sha256_file(args.cohort)
    artifact = build_spatial_artifact(restrictions, segments, matches, source_snapshot=source_snapshot, source_artifacts=source_artifacts)
    write_spatial_artifact(args.output, artifact)
    print({"output": str(args.output), "artifact_sha256": sha256_file(args.output), "integrity": artifact["integrity"], "source_artifact_count": len(source_artifacts)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())