"""Evaluate selected deterministic Phase 12-style experiment records from JSON."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .classify import assess
from .models import AssessmentInput


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON object or list of assessment input objects")
    arguments = parser.parse_args()
    payload = json.loads(arguments.input.read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else [payload]
    results = [asdict(assess(AssessmentInput(**record))) for record in records]
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()