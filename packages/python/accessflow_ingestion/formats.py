"""Non-transforming validation for selected raw resource representations."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path


class ResourceFormatError(ValueError):
    """Raised when an official raw representation cannot be structurally parsed."""


def inspect_road_restrictions_csv(path: Path) -> dict[str, object]:
    """Validate the official CSV preamble/header and geometry-bearing fields.

    This reads source rows without rewriting, normalizing, or persisting them.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if {"ID", "Latitude", "Longitude", "GeoPolyline"}.issubset(row)
        ),
        None,
    )
    if header_index is None:
        raise ResourceFormatError("Road Restrictions CSV has no verified geometry-bearing header")
    header = rows[header_index]
    data_rows = rows[header_index + 1 :]
    if not data_rows or any(len(row) != len(header) for row in data_rows):
        raise ResourceFormatError("Road Restrictions CSV contains inconsistent row widths")
    return {
        "header_index": header_index,
        "column_count": len(header),
        "row_count": len(data_rows),
        "geometry_columns": ["Latitude", "Longitude", "GeoPolyline"],
        "header": header,
    }


def inspect_road_restrictions_xml(path: Path) -> dict[str, object]:
    """Validate the official XML structure without rewriting source rows."""
    root = ET.parse(path).getroot()
    closures = list(root.findall("Closure"))
    if root.tag != "Closures" or not closures:
        raise ResourceFormatError("Road Restrictions XML has no verified Closures structure")
    fields = {child.tag for child in closures[0]}
    required = {"Id", "Latitude", "Longitude"}
    if not required.issubset(fields):
        raise ResourceFormatError("Road Restrictions XML lacks verified location fields")
    return {
        "root": root.tag,
        "closure_count": len(closures),
        "location_fields": sorted(required),
        "first_closure_fields": sorted(fields),
    }