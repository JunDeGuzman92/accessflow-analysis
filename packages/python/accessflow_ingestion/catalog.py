"""Toronto Open Data catalogue discovery for the Phase 9 datasets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    dataset_id: str
    resource_name: str
    resource_format: str


PHASE9_DATASETS = {
    "pedestrian-network": DatasetSpec(
        key="pedestrian-network",
        dataset_id="pedestrian-network",
        resource_name="Pedestrian Network Data - 4326.gpkg",
        resource_format="gpkg",
    ),
    "road-restrictions": DatasetSpec(
        key="road-restrictions",
        dataset_id="road-restrictions",
        resource_name="Road Restrictions (Version 3) - XML",
        resource_format="xml",
    ),
}


class CatalogueError(RuntimeError):
    """Raised when catalogue metadata cannot be retrieved or selected."""


def fetch_package(dataset_id: str, api_base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    """Retrieve one package record from the official CKAN API."""
    url = f"{api_base.rstrip('/')}/package_show?id={quote(dataset_id)}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except Exception as exc:  # pragma: no cover - network-specific errors
        raise CatalogueError(f"Unable to retrieve catalogue metadata: {url}") from exc
    if not payload.get("success") or not isinstance(payload.get("result"), dict):
        raise CatalogueError(f"Catalogue returned no package metadata for {dataset_id}")
    return payload["result"]


def select_resource(package: dict[str, Any], spec: DatasetSpec) -> dict[str, Any]:
    """Select the explicitly approved resource by official name and format."""
    resources = package.get("resources", [])
    matches = [
        resource
        for resource in resources
        if resource.get("name") == spec.resource_name
        and str(resource.get("format", "")).lower() == spec.resource_format.lower()
    ]
    if len(matches) != 1:
        available = [
            {"name": item.get("name"), "format": item.get("format"), "id": item.get("id")}
            for item in resources
        ]
        raise CatalogueError(
            f"Expected exactly one approved resource for {spec.key}; found {len(matches)}. "
            f"Available resources: {available}"
        )
    resource = matches[0]
    if not resource.get("url") or not resource.get("id"):
        raise CatalogueError(f"Selected resource for {spec.key} lacks a URL or resource ID")
    return resource


def discover(spec: DatasetSpec, api_base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    """Return selected resource metadata plus the relevant package metadata."""
    package = fetch_package(spec.dataset_id, api_base)
    resource = select_resource(package, spec)
    return {
        "dataset": {
            "key": spec.key,
            "package_id": package.get("id"),
            "catalogue_name": package.get("name"),
            "title": package.get("title"),
            "owner_division": package.get("owner_division"),
            "refresh_rate": package.get("refresh_rate"),
            "license_title": package.get("license_title"),
            "last_refreshed": package.get("last_refreshed"),
            "metadata_modified": package.get("metadata_modified"),
        },
        "resource": {
            "id": resource.get("id"),
            "name": resource.get("name"),
            "format": resource.get("format"),
            "url": resource.get("url"),
            "size": resource.get("size"),
            "last_modified": resource.get("last_modified"),
            "metadata_modified": resource.get("metadata_modified"),
        },
    }
