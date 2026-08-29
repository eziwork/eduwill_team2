from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from validate_intake import load_intake, validate_intake


def _load_registry(script_dir: Path) -> dict[str, Any]:
    return json.loads((script_dir.parent / "references" / "source-registry.json").read_text(encoding="utf-8"))


def _transaction_route(registry: dict[str, Any], property_type: str, trade_type: str) -> str | None:
    for source_id, source in registry.get("sources", {}).items():
        if source.get("provider") != "MOLIT_RTMS":
            continue
        for support in source.get("supports", []):
            if support.get("property_type") == property_type and support.get("trade_type") == trade_type:
                return source_id
    return None


def plan_sources(data: dict[str, Any], registry: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    property_type = str(data["target"]["property_type"])
    trade_type = str(data["transaction"]["trade_type"])
    route = _transaction_route(registry, property_type, trade_type)
    selected: list[dict[str, Any]] = []
    limitations: list[str] = []

    if route:
        source = registry["sources"][route]
        selected.append(
            {
                "source_id": route,
                "authority": source["authority"],
                "provider": source["provider"],
                "dataset_id": source.get("dataset_id"),
                "credential_ref": source.get("credential_ref"),
                "adapter_status": "IMPLEMENTED",
                "required": data.get("evidence_mode") == "actual",
            }
        )
    else:
        limitations.append(f"{property_type}/{trade_type} has no bundled official unit-level transaction route")

    collection = data.get("collection", {})
    listings_value = collection.get("listings_path")
    listings_path = None
    if isinstance(listings_value, str) and listings_value.strip():
        candidate = Path(listings_value)
        listings_path = candidate if candidate.is_absolute() else base_dir / candidate
    if collection.get("include_current_market", True):
        selected.append(
            {
                "source_id": "USER_PROVIDED_LISTINGS" if listings_path and listings_path.is_file() else "NAVER_PAY_LAND_BROWSER",
                "authority": "USER_PROVIDED" if listings_path and listings_path.is_file() else "BROWSER_OBSERVED",
                "provider": "USER_FILE" if listings_path and listings_path.is_file() else "NAVER_PAY_LAND",
                "credential_ref": None,
                "adapter_status": "READY_INPUT" if listings_path and listings_path.is_file() else "MANUAL_OR_BROWSER_SAMPLE",
                "required": data.get("task_mode") == "MARKET_REPORT_WITH_MATCHING",
            }
        )
        if not listings_path:
            limitations.append("current listings require an in-app checked sample or a user-provided JSON/CSV")

    if data.get("task_mode") == "MARKET_REPORT_WITH_MATCHING":
        selected.append(
            {
                "source_id": "MATCHING_CANDIDATES",
                "authority": "USER_PROVIDED",
                "provider": "USER_FILE",
                "credential_ref": None,
                "adapter_status": "READY_INPUT",
                "required": True,
            }
        )

    if data.get("evidence_mode") == "demo":
        status = "DEMO_READY"
    elif not route:
        status = "PARTIAL_ROUTE"
    else:
        status = "READY_TO_COLLECT"

    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "property_type": property_type,
        "trade_type": trade_type,
        "status": status,
        "transaction_source_id": route,
        "selected_sources": selected,
        "not_automatic": ["BUILDING_HUB", "VWORLD_LAND_CONTEXT", "KOSIS_NEIGHBORHOOD", "ASIL_BROWSER"],
        "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan implemented and manual evidence sources.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = load_intake(args.input)
        errors, warnings = validate_intake(data, args.input.resolve().parent)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 2
        registry = _load_registry(Path(__file__).resolve().parent)
        result = plan_sources(data, registry, args.input.resolve().parent)
        result["warnings"] = warnings
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        print(payload)
        return 0
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

