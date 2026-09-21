"""Generate restriction location names from the committed road restrictions feed snapshot.

Extracts the publisher-provided location fields (Road, Name, FromRoad, ToRoad)
for each closure so the console can show real place names instead of opaque IDs.
All values come verbatim from the source XML; nothing is synthesized.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    snapshots = sorted((REPO / "fixtures").glob("road-restrictions--resource-*.xml"))
    if not snapshots:
        print("ERROR: road restrictions XML snapshot missing from fixtures/", file=sys.stderr)
        return 1
    root = ET.parse(snapshots[0]).getroot()

    locations: dict[str, dict[str, str]] = {}
    for closure in root.findall("Closure"):
        closure_id = closure.findtext("Id")
        if not closure_id:
            continue
        record = {
            "road": (closure.findtext("Road") or "").strip(),
            "name": (closure.findtext("Name") or "").strip(),
            "from_road": (closure.findtext("FromRoad") or "").strip(),
            "to_road": (closure.findtext("ToRoad") or "").strip(),
        }
        if any(record.values()):
            locations[closure_id] = record

    output = REPO / "data" / "processed" / "restriction-locations.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(locations, indent=2), encoding="utf-8")
    print(f"wrote {len(locations)} restriction location names to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
