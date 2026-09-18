"""Command-line interface for Phase 9 acquisition and Phase 10 profiling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import DEFAULT_API_BASE, PHASE9_DATASETS, CatalogueError, discover
from .storage import download_dataset, validate_manifest
from packages.python.accessflow_profiling.phase10 import profile_sources
from packages.python.accessflow_spatial.matching import (
    load_network_segments,
    match_restrictions,
    parse_restrictions,
    select_validation_cases,
    summarize_matches,
    threshold_summary,
    write_validation_csv,
    write_validation_geojson,
)

DEFAULT_RAW_DIR = Path("data/raw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AccessFlow Toronto Phase 9 ingestion and Phase 10 profiling")
    parser.add_argument("command", choices=["inspect", "download", "validate", "profile", "match"])
    parser.add_argument("--dataset", choices=["pedestrian-network", "road-restrictions", "both"], default="both")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--force", action="store_true", help="download a new immutable payload")
    parser.add_argument("--validation-output", type=Path, help="write a small Phase 11 review CSV")
    parser.add_argument("--validation-geojson-dir", type=Path, help="write selected Phase 11 review GeoJSON files")
    return parser.parse_args()


def selected_keys(dataset: str) -> list[str]:
    return list(PHASE9_DATASETS) if dataset == "both" else [dataset]


def main() -> int:
    args = parse_args()
    if args.command == "validate":
        manifests = sorted((args.raw_dir / "manifests").glob("*.json"))
        results = [validate_manifest(path) for path in manifests]
        print(json.dumps(results, indent=2))
        return 0 if all(item["valid"] for item in results) else 1

    if args.command == "profile":
        road = next(args.raw_dir.glob("road-restrictions--resource-*.xml"), None)
        pedestrian = next(args.raw_dir.glob("pedestrian-network--resource-*.gpkg"), None)
        if road is None or pedestrian is None:
            print(json.dumps({"error": "canonical Phase 9 raw resources are missing"}, indent=2))
            return 1
        print(json.dumps(profile_sources(road, pedestrian), indent=2, sort_keys=True))
        return 0

    if args.command == "match":
        road = next(args.raw_dir.glob("road-restrictions--resource-*.xml"), None)
        pedestrian = next(args.raw_dir.glob("pedestrian-network--resource-*.gpkg"), None)
        if road is None or pedestrian is None:
            print(json.dumps({"error": "canonical Phase 9 raw resources are missing"}, indent=2))
            return 1
        restrictions = parse_restrictions(road)
        segments = load_network_segments(pedestrian)
        results = match_restrictions(restrictions, segments)
        selected_cases = select_validation_cases(results)
        geojson_outputs = []
        if args.validation_output:
            args.validation_output.parent.mkdir(parents=True, exist_ok=True)
            write_validation_csv(args.validation_output, results)
        if args.validation_geojson_dir:
            geojson_outputs = write_validation_geojson(
                args.validation_geojson_dir,
                selected_cases,
                {restriction.restriction_id: restriction for restriction in restrictions},
                {segment.segment_id: segment for segment in segments},
            )
        print(json.dumps({
            "summary_at_5_metres": summarize_matches(results),
            "thresholds": threshold_summary(results),
            "validation_output": str(args.validation_output) if args.validation_output else None,
            "validation_cases": [
                {"restriction_id": result.restriction_id, "selection_reason": reason}
                for result, reason in selected_cases
            ],
            "validation_geojson_outputs": [str(path) for path in geojson_outputs],
        }, indent=2))
        return 0

    try:
        discovered = [discover(PHASE9_DATASETS[key], args.api_base) for key in selected_keys(args.dataset)]
    except CatalogueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    if args.command == "inspect":
        print(json.dumps(discovered, indent=2))
        return 0

    results = [download_dataset(item, args.raw_dir, force=args.force) for item in discovered]
    print(json.dumps([{key: str(value) for key, value in result.items()} for result in results], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
