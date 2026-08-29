from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OPERATORS = {"eq", "neq", "lt", "lte", "gt", "gte", "in", "contains", "between"}


def _read_json(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return {}, [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("candidate JSON must be an object or list")
    rows = payload.get("listings", payload.get("candidates", []))
    if not isinstance(rows, list):
        raise ValueError("candidate JSON listings/candidates must be a list")
    return payload.get("source", {}) if isinstance(payload.get("source"), dict) else {}, [item for item in rows if isinstance(item, dict)]


def load_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _read_json(path)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return {}, [dict(row) for row in csv.DictReader(handle)]
    raise ValueError("candidate file must be JSON or CSV")


def _get(record: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    value: Any = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value or value[part] in (None, ""):
            return False, None
        value = value[part]
    return True, value


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    return float(str(value).replace(",", ""))


def evaluate(value: Any, operator: str, expected: Any) -> bool:
    if operator not in OPERATORS:
        raise ValueError(f"unsupported operator: {operator}")
    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "in":
        return value in expected
    if operator == "contains":
        return expected in value
    if operator == "between":
        low, high = expected
        actual = _number(value)
        return _number(low) <= actual <= _number(high)
    actual = _number(value)
    target = _number(expected)
    return {"lt": actual < target, "lte": actual <= target, "gt": actual > target, "gte": actual >= target}[operator]


def _dedup_key(row: dict[str, Any]) -> tuple[Any, ...]:
    listing_id = row.get("listing_id")
    if listing_id not in (None, ""):
        return ("id", str(listing_id).strip().lower())
    return (
        "tuple",
        str(row.get("name", "")).strip().lower(),
        row.get("price_krw"),
        row.get("deposit_krw"),
        row.get("monthly_rent_krw"),
        row.get("exclusive_area_sqm"),
        row.get("floor"),
    )


def deduplicate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        key = _dedup_key(row)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        result.append(row)
    return result, duplicates


def _criterion_result(row: dict[str, Any], criterion: dict[str, Any]) -> tuple[str, str]:
    field = str(criterion.get("field", ""))
    label = str(criterion.get("label") or field)
    exists, value = _get(row, field)
    if not exists:
        return "UNKNOWN", label
    try:
        passed = evaluate(value, str(criterion.get("operator", "")), criterion.get("value"))
    except (TypeError, ValueError):
        return "UNKNOWN", label
    return ("PASS" if passed else "FAIL"), label


def match_candidates(rows: list[dict[str, Any]], must_haves: list[dict[str, Any]], preferences: list[dict[str, Any]]) -> dict[str, Any]:
    deduped, duplicate_count = deduplicate(rows)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for original_index, row in enumerate(deduped):
        must_results = [_criterion_result(row, item) for item in must_haves]
        failed_must = [label for status, label in must_results if status == "FAIL"]
        unknown_must = [label for status, label in must_results if status == "UNKNOWN"]
        if failed_must:
            excluded.append({"candidate": row, "failed_must_haves": failed_must})
            continue
        preference_results = [_criterion_result(row, item) for item in preferences]
        matched = [label for status, label in preference_results if status == "PASS"]
        failed = [label for status, label in preference_results if status == "FAIL"]
        unknown = [label for status, label in preference_results if status == "UNKNOWN"]
        score = round(len(matched) / len(preferences) * 100, 2) if preferences else 100.0
        included.append(
            {
                "candidate": row,
                "must_have_status": "NEEDS_REVIEW" if unknown_must else "PASS",
                "score": score,
                "matched_preferences": matched,
                "failed_preferences": failed,
                "unknown_conditions": unknown_must + unknown,
                "_original_index": original_index,
            }
        )
    included.sort(key=lambda item: (0 if item["must_have_status"] == "PASS" else 1, -item["score"], item["_original_index"]))
    for item in included:
        item.pop("_original_index", None)
    return {
        "input_count": len(rows),
        "deduplicated_count": len(deduped),
        "duplicate_count": duplicate_count,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "results": included,
        "excluded": excluded,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply must-have filters and equal-weight preference scoring.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        source, rows = load_candidates(args.input)
        criteria = json.loads(args.criteria.read_text(encoding="utf-8"))
        result = match_candidates(rows, criteria.get("must_haves", []), criteria.get("preferences", []))
        result["source"] = source
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        print(payload)
        return 0
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

