from __future__ import annotations

import argparse
from pathlib import Path

from build_report import load_request, validate_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a real-estate client report request JSON.")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        data = load_request(args.input)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    errors = validate_request(data)
    audit = data.get("_evidence_audit", {})
    for warning in audit.get("warnings", []):
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print(f"PASS: request schema and evidence audit ({audit.get('derived_release_status', 'UNKNOWN')})")
    print(f"FINGERPRINT: {audit.get('evidence_fingerprint', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
