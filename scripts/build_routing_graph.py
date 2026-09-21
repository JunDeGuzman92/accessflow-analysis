"""Build the pedestrian routing graph artifact from the real Toronto network GeoPackage.

Reads the same source used by the analytical pipeline (data/raw pedestrian network GPKG),
builds an undirected walking graph with endpoint clustering, and serializes it as a
dependency-free pickle consumed by the API routing endpoint.

Design notes (documented choices, no fabricated data):
- pyproj is unavailable in this environment (DLL policy block), so edge lengths are
  computed with the haversine formula over WGS84 vertices — a standard geodesic
  approximation (~0.5% of UTM 17N lengths at Toronto latitude).
- Endpoint clustering tolerance is expressed in degrees (1e-6 deg ~ 0.11 m) using the
  same grid-bucket + union-find approach as the analytical pipeline, which used 1 mm
  in projected metres.
- Barrier sets (restriction -> candidate segment IDs) come from the authoritative
  phase22-spatial.json artifact; candidate segments are evidence, not confirmed
  closures, and the routing API preserves that limitation.
"""

from __future__ import annotations

import json
import math
import pickle
import sqlite3
import sys
import time
from pathlib import Path

from shapely import wkb
from shapely.geometry import LineString, MultiLineString

REPO = Path(__file__).resolve().parents[1]
GPKG_GLOB = "pedestrian-network--resource-*.gpkg"
TOLERANCE_DEG = 1e-6
OUTPUT = REPO / "data" / "processed" / "routing-graph.pkl"
SPATIAL_ARTIFACT = REPO / "data" / "processed" / "phase22-spatial.json"

EARTH_RADIUS_M = 6371008.8


def read_wkb_geometry(blob: bytes):
    if len(blob) < 8 or blob[:2] != b"GP":
        raise ValueError("invalid GeoPackage geometry header")
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0b111
    envelope_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(envelope_indicator)
    if envelope_size is None or flags & 0x10:
        raise ValueError("empty or unsupported GeoPackage geometry envelope")
    geometry = wkb.loads(blob[8 + envelope_size :])
    if geometry.is_empty:
        return None
    return geometry


def load_segments(path: Path):
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        content = connection.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
        ).fetchall()
        if len(content) != 1:
            raise ValueError(f"expected exactly one feature table, found {len(content)}")
        table_name = content[0][0]
        geometry_column = connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?", (table_name,)
        ).fetchone()[0]
        columns = connection.execute(
            f'PRAGMA table_info("{table_name.replace(chr(34), chr(34) * 2)}")'
        ).fetchall()
        attribute_columns = [column[1] for column in columns if column[1] != geometry_column]
        identifier_field = "OBJECTID" if "OBJECTID" in attribute_columns else attribute_columns[0]
        escaped_table = table_name.replace(chr(34), chr(34) * 2)
        selected = ", ".join(
            f'"{column.replace(chr(34), chr(34) * 2)}"'
            for column in attribute_columns + [geometry_column]
        )
        rows = connection.execute(f'SELECT {selected} FROM "{escaped_table}"').fetchall()
        segments = []
        for row in rows:
            attributes = dict(zip(attribute_columns, row[:-1]))
            geometry = read_wkb_geometry(row[-1])
            if geometry is None:
                continue
            character = {
                "road_type": str(attributes["ROAD_TYPE"]).strip() or None,
                "sidewalk": str(attributes["SIDEWALK_DESCRIPTION"]).strip() or None,
                "crosswalk": 1 if attributes.get("CROSSWALK") else 0,
                "px_type": str(attributes["PX_TYPE"]).strip() or None,
            }
            segments.append((str(attributes[identifier_field]), geometry, character))
        return segments
    finally:
        connection.close()


def parts_of(geometry):
    if isinstance(geometry, LineString):
        return [list(geometry.coords)]
    if isinstance(geometry, MultiLineString):
        return [list(line.coords) for line in geometry.geoms if not line.is_empty]
    return []


def haversine_m(a, b):
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        root = item
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(item, item) != item:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb, key=str)] = min(ra, rb, key=str)


def main() -> int:
    started = time.time()
    gpkg_files = sorted((REPO / "data" / "raw").glob(GPKG_GLOB))
    if not gpkg_files:
        print("ERROR: pedestrian network GeoPackage not found in data/raw", file=sys.stderr)
        return 1
    gpkg = gpkg_files[0]
    print(f"Loading segments from {gpkg.name} ...")
    segments = load_segments(gpkg)
    print(f"Loaded {len(segments)} segments ({time.time() - started:.1f}s)")

    uf = UnionFind()
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def cell_of(point):
        return (math.floor(point[0] / TOLERANCE_DEG), math.floor(point[1] / TOLERANCE_DEG))

    edges = []
    for segment_id, geometry, character in segments:
        for part in parts_of(geometry):
            if len(part) < 2:
                continue
            length_m = sum(haversine_m(part[i - 1], part[i]) for i in range(1, len(part)))
            for endpoint in (part[0], part[-1]):
                cell = cell_of(endpoint)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for other in grid.get((cell[0] + dx, cell[1] + dy), []):
                            if (
                                abs(other[0] - endpoint[0]) <= TOLERANCE_DEG
                                and abs(other[1] - endpoint[1]) <= TOLERANCE_DEG
                            ):
                                uf.union(other, endpoint)
                grid.setdefault(cell, []).append(endpoint)
            edges.append(
                {
                    "u": (part[0][0], part[0][1]),
                    "v": (part[-1][0], part[-1][1]),
                    "len_m": length_m,
                    "seg": segment_id,
                    "coords": part,
                    "character": character,
                }
            )

    print(f"Built {len(edges)} edges ({time.time() - started:.1f}s)")

    node_ids: dict[tuple[float, float], int] = {}
    nodes: dict[int, tuple[float, float]] = {}

    def node_id(point):
        root = uf.find(point)
        existing = node_ids.get(root)
        if existing is not None:
            return existing
        new_id = len(node_ids)
        node_ids[root] = new_id
        nodes[new_id] = (root[0], root[1])
        return new_id

    for edge in edges:
        edge["u"] = node_id(edge["u"])
        edge["v"] = node_id(edge["v"])

    print(f"Clustered endpoints into {len(nodes)} nodes ({time.time() - started:.1f}s)")

    barriers: dict[str, list[str]] = {}
    if SPATIAL_ARTIFACT.exists():
        artifact = json.loads(SPATIAL_ARTIFACT.read_text(encoding="utf-8"))
        for restriction_id, record in artifact.get("records", {}).items():
            feature_ids = sorted(
                {
                    match["feature_id"]
                    for match in record.get("matches", [])
                    if match.get("feature_id")
                }
            )
            if feature_ids:
                barriers[restriction_id] = feature_ids
    print(f"Loaded barrier sets for {len(barriers)} restrictions")

    components = {}
    adjacency: dict[int, list[tuple[int, float]]] = {}
    for edge in edges:
        u, v = edge["u"], edge["v"]
        adjacency.setdefault(u, []).append((v, edge["len_m"]))
        adjacency.setdefault(v, []).append((u, edge["len_m"]))

    def mark(start, label):
        stack = [start]
        while stack:
            current = stack.pop()
            if current in components:
                continue
            components[current] = label
            for neighbor, _ in adjacency.get(current, []):
                if neighbor not in components:
                    stack.append(neighbor)

    label = 0
    for edge in edges:
        if edge["u"] not in components:
            mark(edge["u"], label)
            label += 1
        if edge["v"] not in components:
            mark(edge["v"], label)
            label += 1

    component_labels = set(components.values())
    print(f"Graph has {len(component_labels)} connected components")

    data = {
        "schema": "routing-graph-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "length_method": "haversine-wgs84",
        "endpoint_tolerance_deg": TOLERANCE_DEG,
        "nodes": nodes,
        "edges": edges,
        "barriers": barriers,
        "source": {
            "gpkg": gpkg.name,
            "segments": len(segments),
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as handle:
        pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1_000_000:.1f} MB) in {time.time() - started:.1f}s total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
