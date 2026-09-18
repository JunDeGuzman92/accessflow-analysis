"""Immutable raw-resource storage and lightweight provenance manifests."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extension(resource_format: str) -> str:
    value = resource_format.lower().strip().lstrip(".")
    return value or "bin"


def manifest_matches(manifest: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return (
        manifest.get("resource", {}).get("id") == metadata["resource"]["id"]
        and manifest.get("resource", {}).get("url") == metadata["resource"]["url"]
        and manifest.get("resource", {}).get("format") == metadata["resource"]["format"]
        and manifest.get("resource", {}).get("name") == metadata["resource"]["name"]
    )


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"Accept": "application/octet-stream"})
    with urlopen(request, timeout=300) as response, destination.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def download_dataset(
    metadata: dict[str, Any],
    raw_dir: Path,
    *,
    downloader: Callable[[str, Path], None] = _download,
    force: bool = False,
) -> dict[str, Any]:
    """Download one selected resource without overwriting an existing payload."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir = raw_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    key = metadata["dataset"]["key"]
    resource = metadata["resource"]
    resource_id = str(resource["id"])
    extension = safe_extension(str(resource["format"]))
    base = f"{key}--resource-{resource_id}"
    manifest_path = manifest_dir / f"{base}.json"
    payload_path = raw_dir / f"{base}.{extension}"

    if manifest_path.exists() and payload_path.exists() and not force:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_matches(previous, metadata):
            current_checksum = sha256_file(payload_path)
            if current_checksum == previous.get("sha256"):
                return {"status": "skipped", "payload": payload_path, "manifest": manifest_path}

    if payload_path.exists():
        timestamp = utc_now().replace(":", "").replace("-", "")
        payload_path = raw_dir / f"{base}--{timestamp}.{extension}"
        manifest_path = manifest_dir / f"{base}--{timestamp}.json"

    partial_path = payload_path.with_suffix(payload_path.suffix + ".part")
    if partial_path.exists():
        partial_path.unlink()
    downloader(resource["url"], partial_path)
    checksum = sha256_file(partial_path)
    size_bytes = partial_path.stat().st_size
    partial_path.replace(payload_path)

    source_basename = Path(urlparse(resource["url"]).path).name
    original_filename = source_basename if "." in source_basename else None
    previous_manifest = None
    if manifest_path.exists():
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest = {
        "manifest_version": 1,
        "dataset": metadata["dataset"],
        "resource": resource,
        "retrieved_at_utc": utc_now(),
        "original_filename": original_filename,
        "original_resource_name": resource["name"],
        "local_payload": payload_path.name,
        "sha256": checksum,
        "size_bytes": size_bytes,
        "upstream_change_detection": "catalogue metadata and selected-resource identity; live resources may not publish size or validators",
        "content_changed_from_previous": (
            previous_manifest is not None and previous_manifest.get("sha256") != checksum
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "downloaded", "payload": payload_path, "manifest": manifest_path}


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    """Validate a manifest checksum and payload size."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent.parent / manifest["local_payload"]
    actual_size = payload_path.stat().st_size
    actual_checksum = sha256_file(payload_path)
    return {
        "manifest": str(manifest_path),
        "payload": str(payload_path),
        "valid": actual_size == manifest["size_bytes"] and actual_checksum == manifest["sha256"],
        "size_bytes": actual_size,
        "sha256": actual_checksum,
    }
