from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidence_audit import audit_request, write_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit provenance, completeness, calculations, and customer claims.")
    parser.add_argument("input", type=Path, help="Path to report request JSON")
    parser.add_argument("--output", type=Path, help="Optional JSON audit output")
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    result = audit_request(data, args.input.resolve().parent)
    if args.output:
        write_audit(result, args.output)
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")
    for error in result["errors"]:
        print(f"ERROR: {error}")
    print(f"RELEASE: {result['derived_release_status']}")
    print(f"FINGERPRINT: {result['evidence_fingerprint']}")
    return 2 if result["derived_release_status"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
