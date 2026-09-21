"""Convert the City of Toronto 3D Massing shapefile to a WGS84 GeoJSON artifact.

Provenance (recorded per project data-adoption rules):
- Dataset: "3D Massing" — City of Toronto, City Planning division
- Catalog: https://open.toronto.ca/dataset/3d-massing/
- Resource: 3DMassingShapefile_2025_WGS84.zip (retrieved 2026-09-20)
- License: published on the Open Data portal under the Open Government Licence
  for information and illustrative purposes; the notes state the Context
  Massing Model "MUST BE VERIFIED BY THE USER FOR LEGAL OR OFFICIAL USE".
- Geometry: PolygonZ in Web Mercator (EPSG:3857) despite the WGS84 filename;
  converted to WGS84 (EPSG:4326) with the standard spherical inverse mercator
  formulas (pyproj is unavailable in this environment).
- Heights: AVG_HEIGHT field (mean roof height above ground, metres).

Output is clipped to the central Toronto peninsula and split into a grid of
~1.6 km cells so the web client fetches only the cells in view; the map falls
back to OSM building footprints outside the clipped area.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import shapefile

REPO = Path(__file__).resolve().parents[1]
SHP = REPO / "data" / "raw" / "massing-2025" / "3DMassingShapefile_2025_WGS84.shp"
OUTPUT_DIR = REPO / "data" / "processed" / "massing"

# Central Toronto peninsula (downtown core and surroundings)
CLIP_WEST = -79.47
CLIP_EAST = -79.30
CLIP_SOUTH = 43.60
CLIP_NORTH = 43.72

# Grid cell size in degrees (~1.6 km x 1.7 km at this latitude)
CELL_W = 0.02
CELL_H = 0.015

R_MAJOR = 6378137.0


def mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon = (x / R_MAJOR) * 180.0 / math.pi
    lat = math.degrees(math.atan(math.sinh(y / R_MAJOR)))
    return lon, lat


def cell_indices(lon: float, lat: float) -> tuple[int, int]:
    i = math.floor((lon - CLIP_WEST) / CELL_W)
    j = math.floor((CLIP_NORTH - lat) / CELL_H)
    return i, j


def cell_bounds(i: int, j: int) -> list[float]:
    return [
        CLIP_WEST + i * CELL_W,
        CLIP_NORTH - (j + 1) * CELL_H,
        CLIP_WEST + (i + 1) * CELL_W,
        CLIP_NORTH - j * CELL_H,
    ]


def run_full(started: float) -> int:
    """Write the entire city (no clip) as one GeoJSON for tippecanoe input."""
    reader = shapefile.Reader(str(SHP))
    fields = [f[0] for f in reader.fields[1:]]
    idx_avg = fields.index("AVG_HEIGHT")

    output = REPO / "data" / "processed" / "massing-full.geojson"
    output.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    skipped_height = 0
    with output.open("w", encoding="utf-8") as handle:
        handle.write('{"type":"FeatureCollection","features":[')
        first = True
        for sr in reader.iterShapeRecords():
            record = sr.record
            avg_height = record[idx_avg]
            if avg_height is None or avg_height <= 0:
                skipped_height += 1
                continue
            shape = sr.shape
            if not shape.parts:
                continue
            rings: list[list[list[float]]] = []
            points = shape.points
            parts = list(shape.parts) + [len(points)]
            for part_start, part_end in zip(parts, parts[1:]):
                ring = []
                last = None
                for i in range(part_start, part_end):
                    lon, lat = mercator_to_wgs84(points[i][0], points[i][1])
                    lon = round(lon, 5)
                    lat = round(lat, 5)
                    if last is not None and lon == last[0] and lat == last[1]:
                        continue
                    ring.append([lon, lat])
                    last = [lon, lat]
                if len(ring) >= 4:
                    rings.append(ring)
            if not rings:
                continue
            feature = {
                "type": "Feature",
                "properties": {"h": round(avg_height, 1)},
                "geometry": {"type": "Polygon", "coordinates": rings},
            }
            handle.write(("," if not first else "") + json.dumps(feature, separators=(",", ":")))
            first = False
            kept += 1
            if kept % 100000 == 0:
                print(f"  wrote {kept} buildings ({time.time() - started:.0f}s)")
        handle.write("]}")
    print(
        f"wrote {kept} city-wide buildings to {output.name} "
        f"({output.stat().st_size / 1_000_000:.0f} MB) in {time.time() - started:.0f}s | "
        f"skipped {skipped_height} without height"
    )
    return 0


def main() -> int:
    started = time.time()
    if not SHP.exists():
        print(f"ERROR: massing shapefile missing at {SHP}", file=sys.stderr)
        return 1

    full_mode = "--full" in sys.argv
    if full_mode:
        return run_full(started)

    reader = shapefile.Reader(str(SHP))
    fields = [f[0] for f in reader.fields[1:]]
    idx_avg = fields.index("AVG_HEIGHT")

    cells: dict[tuple[int, int], list[dict]] = {}
    kept = 0
    skipped_clip = 0
    skipped_height = 0

    for sr in reader.iterShapeRecords():
        record = sr.record
        avg_height = record[idx_avg]
        if avg_height is None or avg_height <= 0:
            skipped_height += 1
            continue
        shape = sr.shape
        if not shape.parts:
            continue

        rings: list[list[list[float]]] = []
        points = shape.points
        parts = list(shape.parts) + [len(points)]
        for part_start, part_end in zip(parts, parts[1:]):
            ring = []
            last = None
            for i in range(part_start, part_end):
                lon, lat = mercator_to_wgs84(points[i][0], points[i][1])
                lon = round(lon, 5)
                lat = round(lat, 5)
                if last is not None and lon == last[0] and lat == last[1]:
                    continue
                ring.append([lon, lat])
                last = [lon, lat]
            if len(ring) >= 4:
                rings.append(ring)

        if not rings:
            continue
        centroid = rings[0][0]
        if not (CLIP_WEST <= centroid[0] <= CLIP_EAST and CLIP_SOUTH <= centroid[1] <= CLIP_NORTH):
            skipped_clip += 1
            continue

        feature = {
            "type": "Feature",
            "properties": {"h": round(avg_height, 1)},
            "geometry": {"type": "Polygon", "coordinates": rings},
        }
        i, j = cell_indices(centroid[0], centroid[1])
        cells.setdefault((i, j), []).append(feature)
        kept += 1
        if kept % 50000 == 0:
            print(f"  kept {kept} buildings ({time.time() - started:.0f}s)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_cells = {}
    total_bytes = 0
    for (i, j), features in sorted(cells.items()):
        name = f"cell_{i}_{j}"
        path = OUTPUT_DIR / f"{name}.json"
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
            encoding="utf-8",
        )
        total_bytes += path.stat().st_size
        manifest_cells[name] = cell_bounds(i, j)

    manifest = {
        "schema": "massing-grid-v1",
        "cell_size": [CELL_W, CELL_H],
        "clip": [CLIP_WEST, CLIP_SOUTH, CLIP_EAST, CLIP_NORTH],
        "cells": manifest_cells,
        "building_count": kept,
        "provenance": {
            "publisher": "City of Toronto, City Planning",
            "dataset": "3D Massing (Context Massing Model)",
            "resource": "3DMassingShapefile_2025_WGS84.zip",
            "height_field": "AVG_HEIGHT",
            "note": "Illustrative context model; verify before legal or official use.",
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    print(
        f"wrote {kept} buildings in {len(cells)} cells "
        f"({total_bytes / 1_000_000:.1f} MB total, avg {total_bytes / max(1, len(cells)) / 1000:.0f} KB/cell) "
        f"in {time.time() - started:.0f}s | skipped: {skipped_clip} outside clip, "
        f"{skipped_height} without height"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
