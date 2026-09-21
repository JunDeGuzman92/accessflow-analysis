"""Build the walk-services POI layers artifact from Toronto Open Data.

Downloads verified public datasets that can help a pedestrian during a
street-disruption detour, normalizes them into one GeoJSON FeatureCollection,
and records provenance. Field names below were confirmed against the live
resources; nothing is synthesized.

Sources (Toronto Open Data, Open Government Licence where specified):
  - Street Furniture - Bench                     (rest points)
  - Street Furniture - Automated Public Washroom
  - Park Washroom Facilities                     (has ACCESSIBLE_FEATURES)
  - Air Conditioned and Cool Spaces              (heat relief network)
  - Library Branch General Information           (Toronto Public Library)
  - Association of Community Centres             (has accessibility flags)
  - TTC Routes and Schedules (GTFS stops.txt)    (transit stops)
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CKAN_API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/"
USER_AGENT = "AccessFlow-Toronto POI ingestion (civic accessibility research)"
HTTP_TIMEOUT = 120

PACKAGE_IDS = {
    "bench": "street-furniture-bench",
    "street_washroom": "street-furniture-public-washroom",
    "park_washroom": "washroom-facilities",
    "cooling": "air-conditioned-and-cool-spaces-heat-relief-network",
    "library": "library-branch-general-information",
    "community": "association-of-community-centres",
    "transit": "ttc-routes-and-schedules",
}


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read())


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read()


def _wgs84_geojson_resource(package: dict[str, Any]) -> dict[str, Any] | None:
    """Prefer the WGS84 (4326) GeoJSON resource for a package."""
    resources = package.get("resources", [])
    preferred = [
        r for r in resources
        if r.get("format", "").upper() == "GEOJSON"
        and "4326" in (r.get("name", "") + r.get("url", ""))
    ]
    if preferred:
        return preferred[0]
    fallback = [r for r in resources if r.get("format", "").upper() == "GEOJSON"]
    return fallback[0] if fallback else None


def _point_coordinates(feature: dict[str, Any]) -> list[float] | None:
    """Accept Point geometry, or MultiPoint holding a single location."""
    geometry = feature.get("geometry") or {}
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        pair = coords
    elif gtype == "MultiPoint" and isinstance(coords, (list, tuple)) and len(coords) == 1:
        pair = coords[0]
    else:
        return None
    if (
        isinstance(pair, (list, tuple))
        and len(pair) == 2
        and all(isinstance(c, (int, float)) for c in pair)
        and -180 <= pair[0] <= 180
        and -90 <= pair[1] <= 90
    ):
        return [float(pair[0]), float(pair[1])]
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _bench_props(raw: dict[str, Any]) -> dict[str, Any]:
    number = _text(raw.get("ADDRESSNUMBERTEXT"))
    street = _text(raw.get("ADDRESSSTREET"))
    name = f"{number} {street}".strip() or _text(raw.get("FRONTINGSTREET")) or "Bench"
    return {"kind": "bench", "name": name, "details": "Street bench (rest point)"}


def _street_washroom_props(raw: dict[str, Any]) -> dict[str, Any]:
    number = _text(raw.get("ADDRESSNUMBERTEXT"))
    street = _text(raw.get("ADDRESSSTREET"))
    name = f"{number} {street}".strip() or "Automated public washroom"
    return {
        "kind": "washroom",
        "name": name,
        "details": "Automated public washroom",
        "accessible": _text(raw.get("ACCESSIBLE_FEATURES")) or None,
    }


def _park_washroom_props(raw: dict[str, Any]) -> dict[str, Any]:
    name = _text(raw.get("ALTERNATIVE_NAME")) or _text(raw.get("LOCATION")) or "Park washroom"
    hours = _text(raw.get("HOURS"))
    return {
        "kind": "washroom",
        "name": name,
        "details": (f"Park washroom · {hours}" if hours else "Park washroom"),
        "accessible": _text(raw.get("ACCESSIBLE_FEATURES")) or None,
    }


def _cooling_props(raw: dict[str, Any]) -> dict[str, Any]:
    name = _text(raw.get("locationName")) or "Cool space"
    type_desc = _text(raw.get("locationTypeDesc"))
    return {
        "kind": "cooling",
        "name": name,
        "details": (f"Heat relief · {type_desc}" if type_desc else "Heat relief network cool space"),
    }


def _library_props(raw: dict[str, Any]) -> dict[str, Any]:
    name = _text(raw.get("BranchName")) or "Toronto Public Library branch"
    return {"kind": "library", "name": name, "details": "Toronto Public Library"}


def _community_props(raw: dict[str, Any]) -> dict[str, Any]:
    name = _text(raw.get("Association of Community Centre Name")) or "Community centre"
    flags = [
        flag
        for flag in (
            "Accessible" if _text(raw.get("Accessible")) else None,
            "Public washroom" if _text(raw.get("Public Washroom")) else None,
        )
        if flag
    ]
    return {
        "kind": "community",
        "name": name,
        "details": ("Community centre · " + ", ".join(flags)) if flags else "Community centre",
    }


PROPS_BY_KIND = {
    "bench": _bench_props,
    "street_washroom": _street_washroom_props,
    "park_washroom": _park_washroom_props,
    "cooling": _cooling_props,
    "library": _library_props,
    "community": _community_props,
}


def _load_ckan_kinds() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    features: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {
        "schema": "poi-layers-v1",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "publisher": "City of Toronto Open Data",
        "sources": {},
    }
    for kind, package_id in PACKAGE_IDS.items():
        if kind == "transit":
            continue
        package = _get_json(CKAN_API + "package_show?id=" + package_id)["result"]
        resource = _wgs84_geojson_resource(package)
        if resource is None:
            print(f"WARN: {package_id} has no GeoJSON resource; skipped", file=sys.stderr)
            continue
        data = json.loads(_download(resource["url"]))
        raw_features = data.get("features", [])
        kept = 0
        for feature in raw_features:
            coords = _point_coordinates(feature)
            if coords is None:
                continue
            props = PROPS_BY_KIND[kind](feature.get("properties") or {})
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": coords},
                    "properties": props,
                }
            )
            kept += 1
        provenance["sources"][kind] = {
            "dataset_title": package.get("title"),
            "dataset_url": f"https://open.toronto.ca/dataset/{package.get('name', package_id)}/",
            "license": package.get("license_title") or "License not specified",
            "resource_id": resource.get("id"),
            "resource_url": resource.get("url"),
            "feature_count": kept,
        }
        print(f"{kind}: {kept} features")
    return features, provenance


def _load_transit_stops(
    features: list[dict[str, Any]], provenance: dict[str, Any]
) -> None:
    package = _get_json(CKAN_API + "package_show?id=" + PACKAGE_IDS["transit"])["result"]
    zip_resources = [
        r for r in package.get("resources", []) if r.get("format", "").upper() == "ZIP"
    ]
    if not zip_resources:
        print("WARN: TTC GTFS zip not found; transit stops skipped", file=sys.stderr)
        return
    archive = zipfile.ZipFile(io.BytesIO(_download(zip_resources[0]["url"])))
    stops_name = next((n for n in archive.namelist() if n.endswith("stops.txt")), None)
    if stops_name is None:
        print("WARN: GTFS stops.txt missing from archive; transit stops skipped", file=sys.stderr)
        return
    reader = csv.DictReader(io.StringIO(archive.read(stops_name).decode("utf-8", "replace")))
    kept = 0
    for row in reader:
        try:
            lng = float(row.get("stop_lon", ""))
            lat = float(row.get("stop_lat", ""))
        except ValueError:
            continue
        name = _text(row.get("stop_name")) or "TTC stop"
        wheelchair = row.get("wheelchair_boarding", "")
        details = "TTC stop"
        if wheelchair == "1":
            details = "TTC stop · wheelchair accessible"
        elif wheelchair == "2":
            details = "TTC stop · no wheelchair access"
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {"kind": "transit", "name": name, "details": details},
            }
        )
        kept += 1
    provenance["sources"]["transit"] = {
        "dataset_title": package.get("title"),
        "dataset_url": f"https://open.toronto.ca/dataset/{package.get('name', PACKAGE_IDS['transit'])}/",
        "license": package.get("license_title") or "License not specified",
        "resource_id": zip_resources[0].get("id"),
        "resource_url": zip_resources[0].get("url"),
        "feature_count": kept,
    }
    print(f"transit: {kept} features")


def main() -> int:
    features, provenance = _load_ckan_kinds()
    _load_transit_stops(features, provenance)
    if not features:
        print("ERROR: no POI features were collected", file=sys.stderr)
        return 1

    output_dir = REPO / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": features}
    output = output_dir / "poi-layers.geojson"
    output.write_text(json.dumps(collection), encoding="utf-8")
    provenance["feature_count"] = len(features)
    (output_dir / "poi-layers-provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(features)} POI features to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
