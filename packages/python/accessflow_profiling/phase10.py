"""Read-only Phase 10 profiling using Python's standard library only."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import sqlite3
import struct
from typing import Any
import xml.etree.ElementTree as ET


TORONTO_BOUNDS = {"min_longitude": -79.8, "max_longitude": -79.0, "min_latitude": 43.4, "max_latitude": 43.9}
NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
POLYLINE_PATTERN = re.compile(
    rf"^\s*\[\s*({NUMBER_PATTERN})\s*,\s*({NUMBER_PATTERN})\s*\](?:\s*,\s*\[\s*({NUMBER_PATTERN})\s*,\s*({NUMBER_PATTERN})\s*\])+\s*$"
)


def _percent(count: int, total: int) -> float:
    return round(count * 100 / total, 4) if total else 0.0


def _parse_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_epoch_millis(value: str) -> datetime | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    try:
        return datetime.fromtimestamp(parsed / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _infer_type(field: str, values: list[str]) -> str:
    if not values:
        return "blank"
    if field.endswith("Time") or field == "LastUpdated":
        parsed_times = [_parse_epoch_millis(value) for value in values]
        if all(item is not None for item in parsed_times):
            return "epoch_milliseconds_timestamp"
    if all(value in {"0", "1"} for value in values):
        return "binary_indicator_or_enum"
    if all(_parse_float(value) is not None for value in values):
        return "numeric"
    return "text"


def _field_profile(field: str, values: list[str], total: int) -> dict[str, Any]:
    non_empty = [value for value in values if value]
    return {
        "observed_type": _infer_type(field, non_empty),
        "count": total,
        "non_empty_count": len(non_empty),
        "blank_count": total - len(non_empty),
        "blank_percentage": _percent(total - len(non_empty), total),
        "unique_count": len(set(non_empty)),
    }


def _parse_polyline(value: str) -> list[tuple[float, float]] | None:
    if not value or not POLYLINE_PATTERN.fullmatch(value):
        return None
    pairs = re.findall(rf"\[\s*({NUMBER_PATTERN})\s*,\s*({NUMBER_PATTERN})\s*\]", value)
    coordinates = [(float(longitude), float(latitude)) for longitude, latitude in pairs]
    if len(coordinates) < 2 or any(not math.isfinite(value) for pair in coordinates for value in pair):
        return None
    return coordinates


def _extent(coordinate_sets: list[list[tuple[float, float]]]) -> dict[str, float] | None:
    coordinates = [coordinate for coordinate_set in coordinate_sets for coordinate in coordinate_set]
    if not coordinates:
        return None
    longitudes = [coordinate[0] for coordinate in coordinates]
    latitudes = [coordinate[1] for coordinate in coordinates]
    return {
        "min_longitude": min(longitudes),
        "max_longitude": max(longitudes),
        "min_latitude": min(latitudes),
        "max_latitude": max(latitudes),
    }


def _within_bounds(longitude: float, latitude: float, bounds: dict[str, float]) -> bool:
    return bounds["min_longitude"] <= longitude <= bounds["max_longitude"] and bounds["min_latitude"] <= latitude <= bounds["max_latitude"]


def profile_road_restrictions(path: Path) -> dict[str, Any]:
    """Profile the canonical XML without changing its bytes or values."""
    tree = ET.parse(path)
    root = tree.getroot()
    records = list(root)
    field_names = sorted({child.tag for record in records for child in record})
    values_by_field = {
        field: [(record.find(field).text or "").strip() if record.find(field) is not None else "" for record in records]
        for field in field_names
    }
    field_profiles = {field: _field_profile(field, values, len(records)) for field, values in values_by_field.items()}

    identifiers = values_by_field.get("Id", [])
    non_empty_ids = [value for value in identifiers if value]
    latitude_values = values_by_field.get("Latitude", [])
    longitude_values = values_by_field.get("Longitude", [])
    latitude_numbers = [parsed for value in latitude_values if value and (parsed := _parse_float(value)) is not None]
    longitude_numbers = [parsed for value in longitude_values if value and (parsed := _parse_float(value)) is not None]
    latitude_failures = sum(value != "" and _parse_float(value) is None for value in latitude_values)
    longitude_failures = sum(value != "" and _parse_float(value) is None for value in longitude_values)
    point_coordinates = [
        (longitude, latitude)
        for latitude, longitude in zip(latitude_numbers, longitude_numbers)
        if latitude is not None and longitude is not None
    ]
    point_extent = _extent([[coordinate] for coordinate in point_coordinates])
    point_outside_toronto = [
        coordinate for coordinate in point_coordinates if not _within_bounds(coordinate[0], coordinate[1], TORONTO_BOUNDS)
    ]

    polylines = values_by_field.get("GeoPolyline", [])
    parsed_polylines = [_parse_polyline(value) for value in polylines if value]
    parsed_polyline_coordinates = [coordinates for coordinates in parsed_polylines if coordinates is not None]
    geometry_extent = _extent(parsed_polyline_coordinates)
    polyline_outside_toronto = [
        coordinate
        for coordinates in parsed_polyline_coordinates
        for coordinate in coordinates
        if not _within_bounds(coordinate[0], coordinate[1], TORONTO_BOUNDS)
    ]

    time_profiles: dict[str, Any] = {}
    for field in ["StartTime", "EndTime", "Planned", "CreatedTime", "LastUpdated"]:
        values = values_by_field.get(field, [])
        parsed = [_parse_epoch_millis(value) for value in values if value] if field != "Planned" else []
        time_profiles[field] = {
            "present": field in values_by_field,
            "parse_success_count": sum(item is not None for item in parsed) if field != "Planned" else None,
            "parse_failure_count": sum(item is None for item in parsed) if field != "Planned" else None,
            "blank_count": sum(not value for value in values),
            "blank_percentage": _percent(sum(not value for value in values), len(records)),
            "min_utc": min(parsed).isoformat() if parsed else None,
            "max_utc": max(parsed).isoformat() if parsed else None,
            "observed_values": sorted(set(values)) if field == "Planned" else None,
        }

    exact_record_hashes = [hashlib.sha256(ET.tostring(record, encoding="utf-8")).hexdigest() for record in records]
    duplicate_hash_counts = Counter(exact_record_hashes)
    duplicate_records = sum(count - 1 for count in duplicate_hash_counts.values() if count > 1)
    record_field_sets = {tuple(sorted(child.tag for child in record)) for record in records}
    return {
        "source": str(path),
        "record_count": len(records),
        "xml": {
            "root": root.tag,
            "root_attributes": dict(root.attrib),
            "namespace_detected": any("}" in element.tag for element in root.iter()),
            "repeating_element": records[0].tag if records else None,
            "record_field_set_count": len(record_field_sets),
            "malformed": False,
        },
        "fields": field_profiles,
        "important_unique_counts": {
            field: field_profiles[field]["unique_count"]
            for field in ["Id", "Road", "FromRoad", "ToRoad", "AtRoad", "RoadClass", "Type", "Planned"]
            if field in field_profiles
        },
        "id_analysis": {
            "non_empty_count": len(non_empty_ids),
            "unique_count": len(set(non_empty_ids)),
            "duplicate_count": len(non_empty_ids) - len(set(non_empty_ids)),
            "unique_within_snapshot": len(non_empty_ids) == len(set(non_empty_ids)) == len(records),
        },
        "coordinates": {
            "latitude": {
                "numeric_success_count": sum(value is not None for value in latitude_numbers),
                "numeric_failure_count": latitude_failures,
                "missing_count": sum(not value for value in latitude_values),
                "minimum": min(latitude_numbers) if latitude_numbers else None,
                "maximum": max(latitude_numbers) if latitude_numbers else None,
                "outside_valid_range_count": sum(value is not None and not -90 <= value <= 90 for value in latitude_numbers),
            },
            "longitude": {
                "numeric_success_count": sum(value is not None for value in longitude_numbers),
                "numeric_failure_count": longitude_failures,
                "missing_count": sum(not value for value in longitude_values),
                "minimum": min(longitude_numbers) if longitude_numbers else None,
                "maximum": max(longitude_numbers) if longitude_numbers else None,
                "outside_valid_range_count": sum(value is not None and not -180 <= value <= 180 for value in longitude_numbers),
            },
            "bounding_box": point_extent,
            "valid_point_count": len(point_coordinates),
            "toronto_bounds_assumption": TORONTO_BOUNDS,
            "outside_assumed_toronto_extent_count": len(point_outside_toronto),
        },
        "geopolyline": {
            "non_empty_count": sum(bool(value) for value in polylines),
            "empty_count": sum(not value for value in polylines),
            "representation": "comma-separated [longitude,latitude] pairs" if any(polylines) else None,
            "parse_success_count": len(parsed_polyline_coordinates),
            "malformed_count": sum(bool(value) for value in polylines) - len(parsed_polyline_coordinates),
            "geometry_types": {"LineString": len(parsed_polyline_coordinates)},
            "bounding_box": geometry_extent,
            "outside_assumed_toronto_extent_coordinate_count": len(polyline_outside_toronto),
        },
        "temporal_fields": time_profiles,
        "exact_duplicate_record_count": duplicate_records,
        "verified_location_fields": [field for field in ["Road", "FromRoad", "ToRoad", "AtRoad", "RoadClass"] if field in field_profiles],
    }


def _read_wkb(data: bytes, offset: int = 0) -> tuple[str, list[list[tuple[float, float]]], int]:
    if offset + 5 > len(data):
        raise ValueError("truncated WKB header")
    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">" if byte_order == 0 else None
    if endian is None:
        raise ValueError("invalid WKB byte order")
    geometry_type = struct.unpack_from(endian + "I", data, offset + 1)[0]
    offset += 5
    if geometry_type == 2:
        if offset + 4 > len(data):
            raise ValueError("truncated LineString count")
        count = struct.unpack_from(endian + "I", data, offset)[0]
        offset += 4
        coordinates = []
        for _ in range(count):
            if offset + 16 > len(data):
                raise ValueError("truncated LineString coordinate")
            coordinates.append(struct.unpack_from(endian + "dd", data, offset))
            offset += 16
        return "LineString", [coordinates], offset
    if geometry_type == 5:
        if offset + 4 > len(data):
            raise ValueError("truncated MultiLineString count")
        count = struct.unpack_from(endian + "I", data, offset)[0]
        offset += 4
        all_lines: list[list[tuple[float, float]]] = []
        for _ in range(count):
            geometry_name, lines, offset = _read_wkb(data, offset)
            if geometry_name != "LineString":
                raise ValueError("MultiLineString contains non-LineString geometry")
            all_lines.extend(lines)
        return "MultiLineString", all_lines, offset
    raise ValueError(f"unsupported WKB geometry type {geometry_type}")


def _parse_gpkg_geometry(blob: bytes) -> tuple[str, list[list[tuple[float, float]]]]:
    if len(blob) < 8 or blob[:2] != b"GP":
        raise ValueError("invalid GeoPackage geometry header")
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0b111
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    envelope_size = envelope_sizes.get(envelope_indicator)
    if envelope_size is None:
        raise ValueError("invalid GeoPackage envelope indicator")
    if flags & 0x10:
        return "EMPTY", []
    byte_order = "<" if flags & 1 else ">"
    wkb_offset = 8 + envelope_size
    geometry_name, lines, end_offset = _read_wkb(blob, wkb_offset)
    if end_offset != len(blob):
        raise ValueError("trailing bytes after WKB geometry")
    return geometry_name, lines


def _geometry_extent(lines: list[list[tuple[float, float]]]) -> dict[str, float] | None:
    return _extent(lines)


def profile_pedestrian_network(path: Path) -> dict[str, Any]:
    """Profile GeoPackage metadata, attributes, and geometry blobs read-only."""
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        contents = connection.execute(
            "SELECT table_name, data_type, srs_id, min_x, min_y, max_x, max_y FROM gpkg_contents WHERE data_type = 'features'"
        ).fetchall()
        geometry_rows = connection.execute(
            "SELECT table_name, column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns"
        ).fetchall()
        if len(contents) != 1:
            raise ValueError(f"expected one feature table, found {len(contents)}")
        table_name, data_type, content_srs_id, min_x, min_y, max_x, max_y = contents[0]
        geometry_table = next(row for row in geometry_rows if row[0] == table_name)
        geometry_column = geometry_table[1]
        declared_geometry_type = geometry_table[2]
        srs_id = geometry_table[3]
        columns = connection.execute(f'PRAGMA table_info("{table_name.replace(chr(34), chr(34) * 2)}")').fetchall()
        attribute_columns = [column for column in columns if column[1] != geometry_column]
        feature_count = connection.execute(f'SELECT COUNT(*) FROM "{table_name.replace(chr(34), chr(34) * 2)}"').fetchone()[0]
        select_columns = ", ".join(f'"{column[1].replace(chr(34), chr(34) * 2)}"' for column in attribute_columns)
        rows = connection.execute(f'SELECT {select_columns}, "{geometry_column}" FROM "{table_name.replace(chr(34), chr(34) * 2)}"').fetchall()
        attribute_profiles: dict[str, Any] = {}
        for index, column in enumerate(attribute_columns):
            values = [row[index] for row in rows]
            non_null = [value for value in values if value is not None and not (isinstance(value, str) and not value.strip())]
            attribute_profiles[column[1]] = {
                "declared_type": column[2],
                "primary_key": bool(column[5]),
                "non_null_count": len(non_null),
                "null_or_blank_count": feature_count - len(non_null),
                "null_or_blank_percentage": _percent(feature_count - len(non_null), feature_count),
                "unique_count": len({repr(value) for value in non_null}),
                "observed_python_types": sorted({type(value).__name__ for value in non_null}),
            }

        geometry_types: Counter[str] = Counter()
        geometry_errors = 0
        null_geometry_count = 0
        empty_geometry_count = 0
        invalid_geometry_count = 0
        geometry_hashes: Counter[str] = Counter()
        geometry_coordinate_sets: list[list[tuple[float, float]]] = []
        for row in rows:
            blob = row[-1]
            if blob is None:
                null_geometry_count += 1
                continue
            geometry_hashes[hashlib.sha256(blob).hexdigest()] += 1
            try:
                geometry_name, lines = _parse_gpkg_geometry(blob)
                geometry_types[geometry_name] += 1
                if geometry_name == "EMPTY":
                    empty_geometry_count += 1
                elif not lines or any(len(line) < 2 for line in lines) or any(
                    not math.isfinite(value) for line in lines for coordinate in line for value in coordinate
                ):
                    invalid_geometry_count += 1
                else:
                    geometry_coordinate_sets.extend(lines)
            except (ValueError, struct.error):
                geometry_errors += 1
                invalid_geometry_count += 1

        geometry_bbox = _extent(geometry_coordinate_sets)
        crs_row = connection.execute(
            "SELECT organization, organization_coordsys_id, definition, description FROM gpkg_spatial_ref_sys WHERE srs_id = ?",
            (srs_id,),
        ).fetchone()
        topology_fields = [
            column[1]
            for column in attribute_columns
            if any(token in column[1].lower() for token in ["node", "network", "topolog", "from", "to", "connect", "segment"])
        ]
        duplicate_geometry_count = sum(count - 1 for count in geometry_hashes.values() if count > 1)
        return {
            "source": str(path),
            "table": {
                "name": table_name,
                "data_type": data_type,
                "feature_count": feature_count,
                "columns": attribute_profiles,
                "geometry_column": geometry_column,
                "declared_geometry_type": declared_geometry_type,
                "geometry_type_distribution": dict(geometry_types),
                "srs_id": srs_id,
                "content_srs_id": content_srs_id,
                "gpkg_bbox": {"min_longitude": min_x, "min_latitude": min_y, "max_longitude": max_x, "max_latitude": max_y},
                "observed_geometry_bbox": geometry_bbox,
                "null_geometry_count": null_geometry_count,
                "empty_geometry_count": empty_geometry_count,
                "invalid_geometry_count": invalid_geometry_count,
                "geometry_parse_error_count": geometry_errors,
                "valid_geometry_count": feature_count - null_geometry_count - empty_geometry_count - invalid_geometry_count,
                "valid_geometry_percentage": _percent(feature_count - null_geometry_count - empty_geometry_count - invalid_geometry_count, feature_count),
                "duplicate_geometry_count_exact_blob": duplicate_geometry_count,
                "candidate_identifier_fields": {
                    field: {
                        "unique_count": profile["unique_count"],
                        "duplicate_count": profile["non_null_count"] - profile["unique_count"],
                    }
                    for field, profile in attribute_profiles.items()
                    if profile["primary_key"] or field.lower() in {"fid", "_id", "objectid", "id"}
                },
                "topology_or_network_named_fields": topology_fields,
            },
            "crs": {
                "srs_id": srs_id,
                "organization": crs_row[0] if crs_row else None,
                "organization_coordsys_id": crs_row[1] if crs_row else None,
                "definition": crs_row[2] if crs_row else None,
                "description": crs_row[3] if crs_row else None,
            },
        }
    finally:
        connection.close()


def profile_sources(road_restrictions: Path, pedestrian_network: Path) -> dict[str, Any]:
    road = profile_road_restrictions(road_restrictions)
    pedestrian = profile_pedestrian_network(pedestrian_network)
    road_extent = road["coordinates"]["bounding_box"]
    pedestrian_extent = pedestrian["table"]["observed_geometry_bbox"]
    overlap = None
    if road_extent and pedestrian_extent:
        overlap = {
            "longitude": max(0.0, min(road_extent["max_longitude"], pedestrian_extent["max_longitude"]) - max(road_extent["min_longitude"], pedestrian_extent["min_longitude"])),
            "latitude": max(0.0, min(road_extent["max_latitude"], pedestrian_extent["max_latitude"]) - max(road_extent["min_latitude"], pedestrian_extent["min_latitude"])),
        }
    point_tree = ET.parse(road_restrictions)
    point_values = [
        (_parse_float((record.find("Longitude").text or "").strip()), _parse_float((record.find("Latitude").text or "").strip()))
        for record in point_tree.getroot()
    ]
    valid_points = [(longitude, latitude) for longitude, latitude in point_values if longitude is not None and latitude is not None]
    points_within_network_extent = sum(
        pedestrian_extent is not None
        and pedestrian_extent["min_longitude"] <= longitude <= pedestrian_extent["max_longitude"]
        and pedestrian_extent["min_latitude"] <= latitude <= pedestrian_extent["max_latitude"]
        for longitude, latitude in valid_points
    )
    return {
        "road_restrictions": road,
        "pedestrian_network": pedestrian,
        "cross_dataset": {
            "road_coordinate_crs_assumption": "WGS 84 longitude/latitude based on numeric coordinate ranges and matching Toronto source resource naming; XML does not declare CRS",
            "pedestrian_crs": "EPSG:4326",
            "point_extent_overlap_dimensions": overlap,
            "road_valid_point_count": len(valid_points),
            "road_points_within_pedestrian_extent_count": points_within_network_extent,
            "metric_crs_recommendation": "EPSG:26917 (NAD83 / UTM zone 17N) for later Toronto-area metre calculations; confirm datum and project requirements before use",
        },
    }