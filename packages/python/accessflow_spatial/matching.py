"""Projected-CRS spatial matching proof for Phase 11."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
import re
import sqlite3
import struct
from typing import Iterable
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import Transformer
from shapely import transform as transform_many
from shapely import wkb
from shapely.geometry import LineString, Point, mapping
from shapely.strtree import STRtree
from shapely.ops import transform

SOURCE_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:26917"
DEFAULT_THRESHOLDS_METRES = (2.0, 5.0, 10.0)
POLYLINE_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
POLYLINE_PATTERN = re.compile(
    rf"^\s*\[\s*({POLYLINE_NUMBER})\s*,\s*({POLYLINE_NUMBER})\s*\](?:\s*,\s*\[\s*({POLYLINE_NUMBER})\s*,\s*({POLYLINE_NUMBER})\s*\])+\s*$"
)


@dataclass(frozen=True)
class RestrictionRecord:
    restriction_id: str
    latitude: float
    longitude: float
    road: str
    from_road: str
    to_road: str
    at_road: str
    polyline_text: str
    line_wgs84: LineString | None
    point_wgs84: Point
    malformed_polyline: bool


@dataclass(frozen=True)
class NetworkSegment:
    segment_id: str
    attributes: dict[str, object]
    geometry_wgs84: object


@dataclass(frozen=True)
class MatchCandidate:
    restriction_id: str
    segment_id: str
    signal: str
    threshold_metres: float | None
    distance_metres: float | None
    confidence: str
    fallback: bool


@dataclass(frozen=True)
class RestrictionMatchSummary:
    restriction_id: str
    malformed_polyline: bool
    road: str
    from_road: str
    to_road: str
    at_road: str
    valid_polyline: bool
    direct_segment_ids: tuple[str, ...]
    proximity_segment_ids_by_threshold: dict[float, tuple[str, ...]]
    fallback_segment_ids_by_threshold: dict[float, tuple[str, ...]]
    candidates: tuple[MatchCandidate, ...]


def parse_polyline(value: str) -> LineString | None:
    """Parse the source representation without repairing malformed values."""
    if not value or not POLYLINE_PATTERN.fullmatch(value):
        return None
    pairs = re.findall(rf"\[\s*({POLYLINE_NUMBER})\s*,\s*({POLYLINE_NUMBER})\s*\]", value)
    coordinates = [(float(longitude), float(latitude)) for longitude, latitude in pairs]
    return LineString(coordinates) if len(coordinates) >= 2 else None


def parse_restrictions(path: Path) -> list[RestrictionRecord]:
    records: list[RestrictionRecord] = []
    for record in ET.parse(path).getroot():
        def value(name: str) -> str:
            child = record.find(name)
            return (child.text or "").strip() if child is not None else ""

        latitude = float(value("Latitude"))
        longitude = float(value("Longitude"))
        polyline_text = value("GeoPolyline")
        line = parse_polyline(polyline_text)
        records.append(
            RestrictionRecord(
                restriction_id=value("Id"),
                latitude=latitude,
                longitude=longitude,
                road=value("Road"),
                from_road=value("FromRoad"),
                to_road=value("ToRoad"),
                at_road=value("AtRoad"),
                polyline_text=polyline_text,
                line_wgs84=line,
                point_wgs84=Point(longitude, latitude),
                malformed_polyline=line is None,
            )
        )
    return records


def _read_wkb_geometry(blob: bytes) -> object:
    if len(blob) < 8 or blob[:2] != b"GP":
        raise ValueError("invalid GeoPackage geometry header")
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0b111
    envelope_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(envelope_indicator)
    if envelope_size is None or flags & 0x10:
        raise ValueError("empty or unsupported GeoPackage geometry envelope")
    geometry = wkb.loads(blob[8 + envelope_size :])
    if not geometry.is_valid or geometry.is_empty:
        raise ValueError("invalid or empty network geometry")
    return geometry


def load_network_segments(path: Path) -> list[NetworkSegment]:
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
        columns = connection.execute(f'PRAGMA table_info("{table_name.replace(chr(34), chr(34) * 2)}")').fetchall()
        attribute_columns = [column[1] for column in columns if column[1] != geometry_column]
        escaped_table = table_name.replace(chr(34), chr(34) * 2)
        selected = ", ".join(f'"{column.replace(chr(34), chr(34) * 2)}"' for column in attribute_columns + [geometry_column])
        rows = connection.execute(f'SELECT {selected} FROM "{escaped_table}"').fetchall()
        segments: list[NetworkSegment] = []
        identifier_field = "OBJECTID" if "OBJECTID" in attribute_columns else attribute_columns[0]
        for row in rows:
            attributes = dict(zip(attribute_columns, row[:-1]))
            geometry = _read_wkb_geometry(row[-1])
            segments.append(NetworkSegment(str(attributes[identifier_field]), attributes, geometry))
        return segments
    finally:
        connection.close()


def transform_geometry(geometry: object, source_crs: str = SOURCE_CRS, target_crs: str = METRIC_CRS) -> object:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def transform_geometries(geometries: list[object], source_crs: str = SOURCE_CRS, target_crs: str = METRIC_CRS) -> list[object]:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    def project_coordinates(coordinates: object) -> object:
        x_values = coordinates[:, 0]
        y_values = coordinates[:, 1]
        projected_x, projected_y = transformer.transform(x_values, y_values)
        return np.column_stack((projected_x, projected_y))

    return list(transform_many(geometries, project_coordinates))


def _query_indices(tree: STRtree, geometry: object) -> list[int]:
    return [int(index) for index in tree.query(geometry, predicate="intersects")]


def match_projected(
    restriction_geometry: object,
    segment_geometries: list[object],
    segment_ids: list[str],
    *,
    thresholds_metres: Iterable[float] = DEFAULT_THRESHOLDS_METRES,
    fallback: bool = False,
    restriction_id: str = "",
) -> RestrictionMatchSummary:
    """Match only projected geometries; geographic-degree distance is rejected."""
    if not segment_geometries:
        raise ValueError("segment_geometries cannot be empty")
    thresholds = tuple(float(threshold) for threshold in thresholds_metres)
    tree = STRtree(segment_geometries)
    direct_indices = _query_indices(tree, restriction_geometry) if not fallback else []
    direct_ids = tuple(sorted(segment_ids[index] for index in direct_indices))
    candidates: list[MatchCandidate] = [
        MatchCandidate(restriction_id, segment_ids[index], "direct_intersection", None, 0.0, "HIGH", False)
        for index in direct_indices
    ]
    threshold_ids: dict[float, tuple[str, ...]] = {}
    for threshold in thresholds:
        nearby_indices = _query_indices(tree, restriction_geometry.buffer(threshold))
        ids = tuple(sorted(segment_ids[index] for index in nearby_indices))
        threshold_ids[threshold] = ids
        for index in nearby_indices:
            distance = float(restriction_geometry.distance(segment_geometries[index]))
            if index not in direct_indices:
                candidates.append(
                    MatchCandidate(
                        restriction_id,
                        segment_ids[index],
                        "point_fallback" if fallback else "proximity",
                        threshold,
                        distance,
                        "LOW" if fallback else "MEDIUM",
                        fallback,
                    )
                )
    return RestrictionMatchSummary(
        restriction_id=restriction_id,
        malformed_polyline=fallback,
        road="",
        from_road="",
        to_road="",
        at_road="",
        valid_polyline=not fallback,
        direct_segment_ids=direct_ids,
        proximity_segment_ids_by_threshold=threshold_ids if not fallback else {},
        fallback_segment_ids_by_threshold=threshold_ids if fallback else {},
        candidates=tuple(candidates),
    )


def match_restrictions(
    restrictions: list[RestrictionRecord],
    segments: list[NetworkSegment],
    *,
    thresholds_metres: Iterable[float] = DEFAULT_THRESHOLDS_METRES,
    source_crs: str = SOURCE_CRS,
    metric_crs: str = METRIC_CRS,
) -> list[RestrictionMatchSummary]:
    """Match all restrictions using projected geometries and explicit signals."""
    if metric_crs == source_crs:
        raise ValueError("distance matching requires a projected CRS, not EPSG:4326")
    restriction_geometries = transform_geometries(
        [item.line_wgs84 or item.point_wgs84 for item in restrictions], source_crs, metric_crs
    )
    segment_geometries = transform_geometries([item.geometry_wgs84 for item in segments], source_crs, metric_crs)
    segment_ids = [item.segment_id for item in segments]
    tree = STRtree(segment_geometries)
    results: list[RestrictionMatchSummary] = []
    thresholds = tuple(float(threshold) for threshold in thresholds_metres)
    for restriction, geometry in zip(restrictions, restriction_geometries):
        fallback = restriction.malformed_polyline
        direct_indices = [] if fallback else _query_indices(tree, geometry)
        direct_ids = tuple(sorted(segment_ids[index] for index in direct_indices))
        candidates: list[MatchCandidate] = [
            MatchCandidate(restriction.restriction_id, segment_ids[index], "direct_intersection", None, 0.0, "HIGH", False)
            for index in direct_indices
        ]
        proximity_by_threshold: dict[float, tuple[str, ...]] = {}
        fallback_by_threshold: dict[float, tuple[str, ...]] = {}
        for threshold in thresholds:
            nearby_indices = _query_indices(tree, geometry.buffer(threshold))
            ids = tuple(sorted(segment_ids[index] for index in nearby_indices))
            if fallback:
                fallback_by_threshold[threshold] = ids
            else:
                proximity_by_threshold[threshold] = ids
            for index in nearby_indices:
                distance = float(geometry.distance(segment_geometries[index]))
                if index not in direct_indices:
                    candidates.append(
                        MatchCandidate(
                            restriction.restriction_id,
                            segment_ids[index],
                            "point_fallback" if fallback else "proximity",
                            threshold,
                            distance,
                            "LOW" if fallback else "MEDIUM",
                            fallback,
                        )
                    )
        results.append(
            RestrictionMatchSummary(
                restriction.restriction_id,
                restriction.malformed_polyline,
                restriction.road,
                restriction.from_road,
                restriction.to_road,
                restriction.at_road,
                not restriction.malformed_polyline,
                direct_ids,
                proximity_by_threshold,
                fallback_by_threshold,
                tuple(candidates),
            )
        )
    return results


def summarize_matches(results: list[RestrictionMatchSummary], threshold_metres: float = 5.0) -> dict[str, object]:
    candidates = [candidate for result in results for candidate in result.candidates if candidate.threshold_metres is None or candidate.threshold_metres == threshold_metres]
    return {
        "total_restrictions_processed": len(results),
        "restrictions_with_valid_polyline": sum(not result.malformed_polyline for result in results),
        "restrictions_using_fallback": sum(result.malformed_polyline for result in results),
        "restrictions_with_at_least_one_candidate_segment": sum(bool(result.direct_segment_ids or result.proximity_segment_ids_by_threshold.get(threshold_metres) or result.fallback_segment_ids_by_threshold.get(threshold_metres)) for result in results),
        "total_candidate_matches": len(candidates),
        "direct_intersection_matches": sum(candidate.signal == "direct_intersection" for candidate in candidates),
        "proximity_only_matches": sum(candidate.signal == "proximity" for candidate in candidates),
        "fallback_matches": sum(candidate.signal == "point_fallback" for candidate in candidates),
        "confidence_distribution": {confidence: sum(candidate.confidence == confidence for candidate in candidates) for confidence in ["HIGH", "MEDIUM", "LOW"]},
    }


def threshold_summary(results: list[RestrictionMatchSummary], thresholds: Iterable[float] = DEFAULT_THRESHOLDS_METRES) -> list[dict[str, object]]:
    return [
        {
            "threshold_metres": threshold,
            "restrictions_with_candidates": sum(bool(result.direct_segment_ids or result.proximity_segment_ids_by_threshold.get(threshold) or result.fallback_segment_ids_by_threshold.get(threshold)) for result in results),
            "candidate_matches": sum(
                len(result.direct_segment_ids)
                + len(set(result.proximity_segment_ids_by_threshold.get(threshold, ())) - set(result.direct_segment_ids))
                + len(result.fallback_segment_ids_by_threshold.get(threshold, ()))
                for result in results
            ),
            "direct_intersections": sum(len(result.direct_segment_ids) for result in results),
            "proximity_only": sum(
                len(set(result.proximity_segment_ids_by_threshold.get(threshold, ())) - set(result.direct_segment_ids))
                for result in results
            ),
            "fallback_matches": sum(len(result.fallback_segment_ids_by_threshold.get(threshold, ())) for result in results),
        }
        for threshold in thresholds
    ]


def write_validation_csv(path: Path, results: list[RestrictionMatchSummary], threshold_metres: float = 5.0) -> None:
    """Write a small human-review summary, never raw geometries."""
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["restriction_id", "road", "from_road", "to_road", "malformed_polyline", "candidate_count", "direct_count", "proximity_count", "fallback_count", "minimum_distance_metres", "confidence_distribution"])
        writer.writeheader()
        for result in results:
            candidates = [candidate for candidate in result.candidates if candidate.threshold_metres is None or candidate.threshold_metres == threshold_metres]
            distances = [candidate.distance_metres for candidate in candidates]
            writer.writerow({
                "restriction_id": result.restriction_id,
                "road": result.road,
                "from_road": result.from_road,
                "to_road": result.to_road,
                "malformed_polyline": result.malformed_polyline,
                "candidate_count": len(candidates),
                "direct_count": sum(candidate.signal == "direct_intersection" for candidate in candidates),
                "proximity_count": sum(candidate.signal == "proximity" for candidate in candidates),
                "fallback_count": sum(candidate.signal == "point_fallback" for candidate in candidates),
                "minimum_distance_metres": min(distances) if distances else "",
                "confidence_distribution": ";".join(f"{confidence}={sum(candidate.confidence == confidence for candidate in candidates)}" for confidence in ["HIGH", "MEDIUM", "LOW"]),
            })


def _candidate_count(result: RestrictionMatchSummary, threshold_metres: float) -> int:
    direct = set(result.direct_segment_ids)
    proximity = set(result.proximity_segment_ids_by_threshold.get(threshold_metres, ())) - direct
    fallback = set(result.fallback_segment_ids_by_threshold.get(threshold_metres, ()))
    return len(direct | proximity | fallback)


def select_validation_cases(results: list[RestrictionMatchSummary], threshold_metres: float = 5.0, count: int = 10) -> list[tuple[RestrictionMatchSummary, str]]:
    """Select deterministic cases covering required evidence categories."""
    selected: list[tuple[RestrictionMatchSummary, str]] = []

    def add(result: RestrictionMatchSummary, reason: str) -> None:
        if result.restriction_id not in {item.restriction_id for item, _ in selected} and len(selected) < count:
            selected.append((result, reason))

    valid = [result for result in results if not result.malformed_polyline]
    direct = [result for result in valid if result.direct_segment_ids]
    proximity_only = [result for result in valid if not result.direct_segment_ids and result.proximity_segment_ids_by_threshold.get(threshold_metres)]
    fallback = [result for result in results if result.malformed_polyline]
    for result in sorted(direct, key=lambda item: item.restriction_id)[:1]:
        add(result, "direct-intersection baseline")
    for result in sorted(direct, key=lambda item: (-_candidate_count(item, threshold_metres), item.restriction_id))[:1]:
        add(result, "dense direct-intersection case")
    for result in sorted(proximity_only, key=lambda item: item.restriction_id)[:1]:
        add(result, "proximity-only baseline")
    for result in sorted(proximity_only, key=lambda item: (-_candidate_count(item, threshold_metres), item.restriction_id))[:1]:
        add(result, "dense proximity-only case")
    for result in fallback:
        add(result, "malformed-polyline point fallback")
    non_empty = [result for result in results if _candidate_count(result, threshold_metres) > 0]
    for result in sorted(non_empty, key=lambda item: (_candidate_count(item, threshold_metres), item.restriction_id)):
        before = len(selected)
        add(result, "less-dense non-empty case")
        if len(selected) > before:
            break
    for result in sorted(results, key=lambda item: (-_candidate_count(item, threshold_metres), item.restriction_id)):
        add(result, "additional high-candidate case")
    return selected


def write_validation_geojson(
    directory: Path,
    selected_cases: list[tuple[RestrictionMatchSummary, str]],
    restrictions_by_id: dict[str, RestrictionRecord],
    segments_by_id: dict[str, NetworkSegment],
    threshold_metres: float = 5.0,
) -> list[Path]:
    """Write one small WGS84 GeoJSON FeatureCollection per selected case."""
    directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for result, reason in selected_cases:
        restriction = restrictions_by_id[result.restriction_id]
        features: list[dict[str, object]] = []
        restriction_geometry = restriction.line_wgs84 or restriction.point_wgs84
        restriction_properties = {
            "feature_role": "restriction_geometry" if restriction.line_wgs84 is not None else "restriction_fallback_point",
            "restriction_id": restriction.restriction_id,
            "match_type": "source_restriction",
            "confidence": "SOURCE",
            "distance_metres": None,
            "Road": restriction.road,
            "FromRoad": restriction.from_road,
            "ToRoad": restriction.to_road,
            "AtRoad": restriction.at_road,
            "malformed_polyline": restriction.malformed_polyline,
            "selection_reason": reason,
        }
        features.append({"type": "Feature", "geometry": mapping(restriction_geometry), "properties": restriction_properties})
        for candidate in result.candidates:
            if candidate.threshold_metres is not None and candidate.threshold_metres != threshold_metres:
                continue
            segment = segments_by_id[candidate.segment_id]
            features.append({
                "type": "Feature",
                "geometry": mapping(segment.geometry_wgs84),
                "properties": {
                    "feature_role": "candidate_affected_segment",
                    "restriction_id": candidate.restriction_id,
                    "segment_id": candidate.segment_id,
                    "match_type": candidate.signal,
                    "confidence": candidate.confidence,
                    "distance_metres": candidate.distance_metres,
                    "threshold_metres": candidate.threshold_metres,
                    "Road": restriction.road,
                    "FromRoad": restriction.from_road,
                    "ToRoad": restriction.to_road,
                    "AtRoad": restriction.at_road,
                    "malformed_polyline": restriction.malformed_polyline,
                },
            })
        output = directory / f"{restriction.restriction_id}.geojson"
        output.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2) + "\n", encoding="utf-8")
        outputs.append(output)
    return outputs
