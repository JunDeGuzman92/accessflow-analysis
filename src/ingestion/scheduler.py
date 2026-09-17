"""Scheduled ingestion of Toronto road restrictions data."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


CKAN_API_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
ROAD_RESTRICTIONS_PACKAGE = "road-restrictions"


class IngestionScheduler:
    """Poll Toronto Open Data for new road restrictions."""

    def __init__(self, data_dir: Path = Path("data"), check_interval_hours: int = 24):
        self.data_dir = data_dir
        self.raw_dir = data_dir / "raw"
        self.processed_dir = data_dir / "processed"
        self.manifest_path = data_dir / "manifest.json"
        self.check_interval = timedelta(hours=check_interval_hours)

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_package_metadata(self) -> Optional[dict]:
        """Fetch package metadata from CKAN API."""
        try:
            url = f"{CKAN_API_BASE}/package_show?id={ROAD_RESTRICTIONS_PACKAGE}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data["result"]
        except Exception as e:
            print(f"Error fetching package metadata: {e}")
        return None

    def _find_xml_resource(self, package: dict) -> Optional[dict]:
        """Find the XML resource in the package."""
        for resource in package.get("resources", []):
            if resource.get("format", "").upper() == "XML":
                return resource
        return None

    def _compute_checksum(self, content: bytes) -> str:
        """Compute SHA-256 checksum."""
        return hashlib.sha256(content).hexdigest()

    def _load_manifest(self) -> dict:
        """Load the last known manifest."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        """Save manifest to disk."""
        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def check_for_updates(self) -> bool:
        """Check if new data is available."""
        package = self._fetch_package_metadata()
        if not package:
            return False

        resource = self._find_xml_resource(package)
        if not resource:
            return False

        current_checksum = resource.get("checksum") or resource.get("hash")
        last_manifest = self._load_manifest()

        if last_manifest.get("checksum") == current_checksum:
            return False

        return True

    def fetch_latest(self) -> Optional[Path]:
        """Download the latest road restrictions XML."""
        package = self._fetch_package_metadata()
        if not package:
            return None

        resource = self._find_xml_resource(package)
        if not resource:
            return None

        url = resource.get("url")
        if not url:
            return None

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            content = resp.content
        except Exception as e:
            print(f"Error downloading resource: {e}")
            return None

        checksum = self._compute_checksum(content)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"road-restrictions_{timestamp}.xml"
        filepath = self.raw_dir / filename

        with open(filepath, "wb") as f:
            f.write(content)

        # Update manifest
        manifest = self._load_manifest()
        manifest["last_fetch"] = datetime.utcnow().isoformat()
        manifest["checksum"] = checksum
        manifest["filename"] = filename
        manifest["size_bytes"] = len(content)
        self._save_manifest(manifest)

        print(f"Downloaded: {filename} ({len(content):,} bytes, {checksum[:16]}...)")
        return filepath

    def parse_restrictions(self, xml_path: Path) -> pd.DataFrame:
        """Parse XML restrictions into a DataFrame."""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        records = []
        for closure in root.findall(".//Closure"):
            record = {}
            for field in closure:
                record[field.tag] = field.text
            records.append(record)
        return pd.DataFrame(records)

    def run_check(self) -> Optional[pd.DataFrame]:
        """Run a full check: see if new data, fetch, parse, return."""
        print(f"[{datetime.utcnow().isoformat()}] Checking for updates...")

        if not self.check_for_updates():
            print("No updates available.")
            return None

        xml_path = self.fetch_latest()
        if not xml_path:
            return None

        df = self.parse_restrictions(xml_path)
        print(f"Parsed {len(df)} restrictions")

        return df

    def get_last_fetch_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful fetch."""
        manifest = self._load_manifest()
        last_fetch = manifest.get("last_fetch")
        if last_fetch:
            return datetime.fromisoformat(last_fetch)
        return None

    def should_check(self) -> bool:
        """Determine if enough time has passed to check again."""
        last_fetch = self.get_last_fetch_time()
        if not last_fetch:
            return True
        return datetime.utcnow() - last_fetch >= self.check_interval
