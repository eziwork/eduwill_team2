from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Iterable


RELEASE_PASS = "PASS"
RELEASE_CONDITIONAL = "PASS WITH CONDITIONS"
RELEASE_HOLD = "HOLD"

EVIDENCE_STATUSES = {
    "COMPLETE",
    "ZERO_RESULT",
    "SAMPLE_ONLY",
    "PARTIAL",
    "BLOCKED",
    "NOT_APPLICABLE",
}

CALCULATION_OPERATIONS = {
    "count",
    "median",
    "min",
    "max",
    "sum",
    "ratio",
    "percent_change",
    "midrank_percentile",
}

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")
SAMPLE_WORDS = ("확인한 표본", "조회한 표본", "표본 매물", "표본 자료")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def _normalized_number(raw: str) -> str:
    text = raw.replace(",", "")
    try:
        value = float(text)
    except ValueError:
        return text
    if value == 0:
        value = 0.0
    return format(value, ".15g")


def _numbers(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float)):
        found.add(_normalized_number(str(value)))
        return found
    if isinstance(value, str):
        return {_normalized_number(match.group(0)) for match in NUMBER_RE.finditer(value)}
    if isinstance(value, dict):
        for item in value.values():
            found.update(_numbers(item))
        return found
    if isinstance(value, list):
        for item in value:
            found.update(_numbers(item))
    return found


def _local_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _select_json(value: Any, dotted_key: str) -> Any:
    selected = value
    if not dotted_key:
        return selected
    for part in dotted_key.split("."):
        if isinstance(selected, list):
            selected = selected[int(part)]
        elif isinstance(selected, dict):
            selected = selected[part]
        else:
            raise KeyError(part)
    return selected


def _require_string(record: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    if not isinstance(record.get(key), str) or not record[key].strip():
        errors.append(f"{label}.{key} is required")


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    return float(value)


def calculate(operation: str, inputs: dict[str, Any]) -> float:
    if operation == "count":
        return float(len(inputs.get("values", [])))
    if operation in {"median", "min", "max", "sum"}:
        values = [_as_float(value) for value in inputs.get("values", [])]
        if not values:
            raise ValueError(f"{operation} needs a non-empty values list")
        if operation == "median":
            return float(statistics.median(values))
        if operation == "min":
            return float(min(values))
        if operation == "max":
            return float(max(values))
        return float(sum(values))
    if operation == "ratio":
        denominator = _as_float(inputs.get("denominator"))
        if denominator == 0:
            raise ValueError("ratio denominator cannot be zero")
        return _as_float(inputs.get("numerator")) / denominator
    if operation == "percent_change":
        previous = _as_float(inputs.get("previous"))
        if previous == 0:
            raise ValueError("percent_change previous cannot be zero")
        return (_as_float(inputs.get("current")) - previous) / previous * 100
    if operation == "midrank_percentile":
        values = [_as_float(value) for value in inputs.get("values", [])]
        target = _as_float(inputs.get("target"))
        if not values:
            raise ValueError("midrank_percentile needs a non-empty values list")
        less = sum(1 for value in values if value < target)
        equal = sum(1 for value in values if math.isclose(value, target, rel_tol=0, abs_tol=1e-12))
        return (less + 0.5 * equal) / len(values) * 100
    raise ValueError(f"unsupported calculation operation: {operation}")


def _iter_component_claims(data: dict[str, Any]) -> Iterable[tuple[str, Any, list[str]]]:
    target = data.get("target", {})
    target_visible = {key: target.get(key, "") for key in ("name", "address", "descriptor")}
    yield "target", target_visible, [str(item) for item in target.get("claim_ids", [])]

    customer = data.get("customer", {})
    customer_visible = {key: customer.get(key, "") for key in ("question", "scope")}
    yield "customer", customer_visible, [str(item) for item in customer.get("claim_ids", [])]

    for index, metric in enumerate(data.get("metrics", []), start=1):
        visible_metric = {"value": metric.get("value", ""), "note": metric.get("note", "")}
        yield f"metrics[{index}]", visible_metric, [str(metric.get("claim_id", ""))]

    overview = data.get("overview", {})
    overview_text = list(overview.get("paragraphs", [])) + [overview.get("takeaway", "")]
    yield "overview", overview_text, [str(item) for item in overview.get("claim_ids", [])]

    for index, section in enumerate(data.get("sections", []), start=1):
        section_text = [
            section.get("title", ""),
            section.get("lead", ""),
            section.get("caption", ""),
            section.get("body", ""),
            section.get("takeaway", ""),
        ]
        yield f"sections[{index}].copy", section_text, [str(item) for item in section.get("claim_ids", [])]
        visual = section.get("visual", {})
        visible_visual = {key: value for key, value in visual.items() if key != "claim_ids"}
        yield f"sections[{index}].visual", visible_visual, [str(item) for item in visual.get("claim_ids", [])]

    summary = data.get("summary", {})
    yield "summary.paragraphs", summary.get("paragraphs", []), [str(item) for item in summary.get("claim_ids", [])]
    for index, card in enumerate(summary.get("cards", []), start=1):
        yield f"summary.cards[{index}]", card.get("body", ""), [str(card.get("claim_id", ""))]

    for index, item in enumerate(data.get("checklist", []), start=1):
        visible_item = {"title": item.get("title", ""), "body": item.get("body", "")}
        yield f"checklist[{index}]", visible_item, [str(item.get("claim_id", ""))]


def audit_request(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, Any]:
    base_dir = (base_dir or Path(data.get("_base_dir", "."))).resolve()
    evidence_mode = str(data.get("evidence_mode", ""))
    errors: list[str] = []
    warnings: list[str] = []
    conditions: list[str] = []
    checks: list[dict[str, Any]] = []

    if evidence_mode not in {"actual", "demo"}:
        errors.append("evidence_mode must be actual or demo")

    sources = data.get("sources", [])
    source_map: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources, start=1):
        label = f"sources[{index}]"
        source_id = str(source.get("id", "")).strip()
        if not source_id:
            errors.append(f"{label}.id is required")
            continue
        if source_id in source_map:
            errors.append(f"duplicate source id: {source_id}")
        source_map[source_id] = source
        for key in ("grade", "name", "url", "as_of", "scope", "limitation"):
            _require_string(source, key, label, errors)
        if evidence_mode == "actual":
            _require_string(source, "lane", label, errors)
            _require_string(source, "retrieved_at", label, errors)
            if not isinstance(source.get("query_conditions"), dict) or not source.get("query_conditions"):
                errors.append(f"{label}.query_conditions must be a non-empty object")
            url = str(source.get("url", ""))
            if not (url.startswith("https://") or url.startswith("http://") or url == "내부 확인 기록 · 외부 링크 없음"):
                errors.append(f"{label}.url needs an original URL or the internal-record label")

    group_map: dict[str, dict[str, Any]] = {}
    artifact_groups: dict[str, set[str]] = {}
    evidence_groups = data.get("evidence_groups", [])
    if evidence_mode == "actual" and not evidence_groups:
        errors.append("actual mode requires evidence_groups")
    conditional_group_ids: set[str] = set()
    for index, group in enumerate(evidence_groups, start=1):
        label = f"evidence_groups[{index}]"
        group_id = str(group.get("id", "")).strip()
        if not group_id:
            errors.append(f"{label}.id is required")
            continue
        if group_id in group_map:
            errors.append(f"duplicate evidence group id: {group_id}")
        group_map[group_id] = group
        _require_string(group, "lane", label, errors)
        status = str(group.get("status", ""))
        if status not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status must be one of {sorted(EVIDENCE_STATUSES)}")
            continue
        for source_id in group.get("source_ids", []):
            if str(source_id) not in source_map:
                errors.append(f"{label} references unknown source id: {source_id}")

        if evidence_mode == "actual" and status != "NOT_APPLICABLE":
            _require_string(group, "completeness_basis", label, errors)
            counts = group.get("counts", {})
            for key in ("raw_rows", "normalized_rows", "excluded_rows", "parse_failed_rows", "used_rows"):
                if not _integer(counts.get(key)):
                    errors.append(f"{label}.counts.{key} must be a non-negative integer")
            if all(_integer(counts.get(key)) for key in ("raw_rows", "normalized_rows", "excluded_rows", "parse_failed_rows", "used_rows")):
                if counts["raw_rows"] != counts["normalized_rows"] + counts["excluded_rows"] + counts["parse_failed_rows"]:
                    errors.append(f"{label} count reconciliation failed: raw != normalized + excluded + parse_failed")
                if counts["used_rows"] > counts["normalized_rows"]:
                    errors.append(f"{label} count reconciliation failed: used_rows > normalized_rows")

            artifacts = group.get("artifacts", [])
            if not artifacts:
                errors.append(f"{label} needs at least one raw or normalized artifact")
            for artifact_index, artifact in enumerate(artifacts, start=1):
                artifact_label = f"{label}.artifacts[{artifact_index}]"
                artifact_path = str(artifact.get("path", "")).strip()
                expected_hash = str(artifact.get("sha256", "")).strip().upper()
                if not artifact_path or not expected_hash:
                    errors.append(f"{artifact_label} needs path and sha256")
                    continue
                resolved = _local_path(artifact_path, base_dir).resolve()
                artifact_groups.setdefault(str(resolved).lower(), set()).add(group_id)
                if not resolved.is_file():
                    errors.append(f"{artifact_label} file not found: {resolved}")
                    continue
                actual_hash = _sha256_bytes(resolved.read_bytes())
                if actual_hash != expected_hash:
                    errors.append(f"{artifact_label} sha256 mismatch")

            coverage = group.get("coverage", {})
            if not isinstance(coverage, dict) or not coverage:
                errors.append(f"{label}.coverage must be a non-empty object")
                coverage = {}
            expected_periods = [str(item) for item in coverage.get("expected_periods", [])]
            completed_periods = [str(item) for item in coverage.get("completed_periods", [])]
            if len(expected_periods) != len(set(expected_periods)) or len(completed_periods) != len(set(completed_periods)):
                errors.append(f"{label}.coverage period lists contain duplicates")
            if status in {"COMPLETE", "ZERO_RESULT"} and expected_periods and set(expected_periods) != set(completed_periods):
                errors.append(f"{label} period coverage is incomplete")
            if bool(expected_periods) != bool(completed_periods):
                errors.append(f"{label} must record both expected_periods and completed_periods")
            expected_pages = coverage.get("expected_pages")
            fetched_pages = coverage.get("fetched_pages")
            if (expected_pages is None) != (fetched_pages is None):
                errors.append(f"{label} must record both expected_pages and fetched_pages")
            if status in {"COMPLETE", "ZERO_RESULT"} and expected_pages is not None and expected_pages != fetched_pages:
                errors.append(f"{label} page coverage is incomplete")
            source_total = coverage.get("source_total_count")
            fetched_rows = coverage.get("fetched_rows")
            if (source_total is None) != (fetched_rows is None):
                errors.append(f"{label} must record both source_total_count and fetched_rows")
            if source_total is not None and fetched_rows is not None and source_total != fetched_rows:
                errors.append(f"{label} source totalCount does not match fetched_rows")
            if status in {"COMPLETE", "ZERO_RESULT"} and not (
                expected_periods or expected_pages is not None or source_total is not None or coverage.get("scope_exhausted") is True
            ):
                errors.append(f"{label} has no auditable completeness proof")
            if status == "COMPLETE" and _integer(counts.get("raw_rows")) and counts.get("raw_rows") == 0:
                errors.append(f"{label} has zero raw rows and must use ZERO_RESULT instead of COMPLETE")
            if status == "ZERO_RESULT" and any(counts.get(key) != 0 for key in ("raw_rows", "normalized_rows", "excluded_rows", "parse_failed_rows", "used_rows")):
                errors.append(f"{label} is ZERO_RESULT but its row counts are not all zero")
            if group.get("errors"):
                errors.append(f"{label} contains unresolved collection errors")

        if status == "BLOCKED" and group.get("required_for_question", False):
            errors.append(f"{label} is required but BLOCKED")
        elif status in {"SAMPLE_ONLY", "PARTIAL"}:
            conditional_group_ids.add(group_id)
            warnings.append(f"{group_id} is {status}; it may be used only by explicitly limited claims")
        elif status == "NOT_APPLICABLE" and group.get("required_for_question", False):
            errors.append(f"{label} cannot be required and NOT_APPLICABLE")

    calculation_map: dict[str, dict[str, Any]] = {}
    calculated_values: dict[str, float] = {}
    calculation_artifacts: dict[str, str] = {}
    for index, calculation in enumerate(data.get("calculations", []), start=1):
        label = f"calculations[{index}]"
        calculation_id = str(calculation.get("id", "")).strip()
        if not calculation_id:
            errors.append(f"{label}.id is required")
            continue
        if calculation_id in calculation_map:
            errors.append(f"duplicate calculation id: {calculation_id}")
        calculation_map[calculation_id] = calculation
        operation = str(calculation.get("operation", ""))
        if operation not in CALCULATION_OPERATIONS:
            errors.append(f"{label}.operation is unsupported: {operation}")
            continue
        if evidence_mode == "actual":
            _require_string(calculation, "unit", label, errors)
            _require_string(calculation, "rounding", label, errors)
            _require_string(calculation, "display_value", label, errors)
        if evidence_mode == "actual":
            input_artifact_path = str(calculation.get("input_artifact_path", "")).strip()
            if not input_artifact_path:
                errors.append(f"{label}.input_artifact_path is required in actual mode")
            else:
                resolved_input = _local_path(input_artifact_path, base_dir).resolve()
                calculation_artifacts[calculation_id] = str(resolved_input).lower()
                if not resolved_input.is_file():
                    errors.append(f"{label}.input_artifact_path file not found: {resolved_input}")
                elif str(resolved_input).lower() not in artifact_groups:
                    errors.append(f"{label}.input_artifact_path is not registered in an evidence group")
                else:
                    try:
                        artifact_json = json.loads(resolved_input.read_text(encoding="utf-8"))
                        artifact_inputs = _select_json(artifact_json, str(calculation.get("input_key", "")))
                        if _canonical(artifact_inputs) != _canonical(calculation.get("inputs", {})):
                            errors.append(f"{label}.inputs differ from the hashed input artifact")
                    except Exception as exc:
                        errors.append(f"{label}.input artifact cannot be read as JSON: {exc}")
        try:
            recalculated = calculate(operation, calculation.get("inputs", {}))
            claimed_output = _as_float(calculation.get("output"))
            tolerance = abs(_as_float(calculation.get("tolerance", 1e-9)))
            calculated_values[calculation_id] = recalculated
            if not math.isclose(recalculated, claimed_output, rel_tol=tolerance, abs_tol=tolerance):
                errors.append(f"{label} output mismatch: claimed {claimed_output}, recalculated {recalculated}")
        except Exception as exc:
            errors.append(f"{label} cannot be reproduced: {exc}")

    claim_map: dict[str, dict[str, Any]] = {}
    claims = data.get("claims", [])
    if evidence_mode == "actual" and not claims:
        errors.append("actual mode requires claims")
    for index, claim in enumerate(claims, start=1):
        label = f"claims[{index}]"
        claim_id = str(claim.get("id", "")).strip()
        if not claim_id:
            errors.append(f"{label}.id is required")
            continue
        if claim_id in claim_map:
            errors.append(f"duplicate claim id: {claim_id}")
        claim_map[claim_id] = claim
        kind = str(claim.get("kind", ""))
        if kind not in {"direct", "calculated", "interpretive"}:
            errors.append(f"{label}.kind must be direct, calculated, or interpretive")
        _require_string(claim, "statement", label, errors)
        source_ids = [str(item) for item in claim.get("source_ids", [])]
        group_ids = [str(item) for item in claim.get("evidence_group_ids", [])]
        if evidence_mode == "actual" and (not source_ids or not group_ids):
            errors.append(f"{label} needs source_ids and evidence_group_ids in actual mode")
        for source_id in source_ids:
            if source_id not in source_map:
                errors.append(f"{label} references unknown source id: {source_id}")
        for group_id in group_ids:
            if group_id not in group_map:
                errors.append(f"{label} references unknown evidence group id: {group_id}")
        linked_group_source_ids = {
            str(source_id)
            for group_id in group_ids
            for source_id in group_map.get(group_id, {}).get("source_ids", [])
        }
        if evidence_mode == "actual" and not set(source_ids).issubset(linked_group_source_ids):
            errors.append(f"{label} cites a source outside its linked evidence groups")
        calculation_id = str(claim.get("calculation_id", "")).strip()
        if kind == "calculated" and not calculation_id:
            errors.append(f"{label} is calculated but has no calculation_id")
        if calculation_id and calculation_id not in calculation_map:
            errors.append(f"{label} references unknown calculation id: {calculation_id}")
        if evidence_mode == "actual" and calculation_id in calculation_artifacts:
            registered_groups = artifact_groups.get(calculation_artifacts[calculation_id], set())
            if not registered_groups.intersection(group_ids):
                errors.append(f"{label} calculation artifact is not part of the claim's evidence groups")
        if kind == "calculated" and calculation_id in calculation_map and "display_value" in claim:
            if str(claim.get("display_value", "")) != str(calculation_map[calculation_id].get("display_value", "")):
                errors.append(f"{label}.display_value differs from calculation {calculation_id}.display_value")
        conditional_use = conditional_group_ids.intersection(group_ids)
        if conditional_use:
            condition = "Incomplete evidence used with explicit sample scope: " + ", ".join(sorted(conditional_use))
            if condition not in conditions:
                conditions.append(condition)
            statement = str(claim.get("statement", ""))
            if str(claim.get("scope", "")) != "sample":
                errors.append(f"{label} uses incomplete evidence but scope is not sample")
            if not any(word in statement for word in SAMPLE_WORDS):
                errors.append(f"{label} must say that it is based on a checked sample")
            if not str(claim.get("limitation", "")).strip():
                errors.append(f"{label} uses incomplete evidence without a limitation")

    for component, visible_value, claim_ids in _iter_component_claims(data):
        claim_ids = [claim_id for claim_id in claim_ids if claim_id]
        if evidence_mode == "actual" and not claim_ids:
            errors.append(f"{component} needs claim_id(s) in actual mode")
            continue
        linked_claims: list[dict[str, Any]] = []
        for claim_id in claim_ids:
            claim = claim_map.get(claim_id)
            if claim is None:
                errors.append(f"{component} references unknown claim id: {claim_id}")
            else:
                linked_claims.append(claim)
        if not linked_claims:
            continue

        allowed_numbers: set[str] = set()
        for claim in linked_claims:
            allowed_numbers.update(_numbers(claim.get("statement", "")))
            allowed_numbers.update(_numbers(claim.get("display_value", "")))
            calculation_id = str(claim.get("calculation_id", "")).strip()
            if calculation_id in calculation_map:
                allowed_numbers.update(_numbers(calculation_map[calculation_id].get("inputs", {})))
                allowed_numbers.update(_numbers(calculation_map[calculation_id].get("output")))
                allowed_numbers.update(_numbers(calculation_map[calculation_id].get("display_value", "")))
        unsupported = sorted(_numbers(visible_value) - allowed_numbers)
        if unsupported:
            errors.append(f"{component} contains numbers not supported by linked claims: {', '.join(unsupported)}")
        uses_incomplete_evidence = any(
            conditional_group_ids.intersection(str(item) for item in claim.get("evidence_group_ids", []))
            for claim in linked_claims
        )
        if uses_incomplete_evidence:
            visible_text = _canonical(visible_value)
            if not any(word in visible_text for word in SAMPLE_WORDS):
                errors.append(f"{component} uses sample/partial evidence without an explicit checked-sample label")

    for index, metric in enumerate(data.get("metrics", []), start=1):
        claim_id = str(metric.get("claim_id", ""))
        claim = claim_map.get(claim_id)
        if claim and "display_value" in claim and str(metric.get("value", "")) != str(claim.get("display_value", "")):
            errors.append(f"metrics[{index}].value differs from claim {claim_id}.display_value")

    if evidence_mode == "actual" and "release_status" in data:
        warnings.append("manual release_status is ignored; the evidence audit derives it")

    release_status = RELEASE_HOLD if errors else (RELEASE_CONDITIONAL if conditions else RELEASE_PASS)
    fingerprint_payload = {
        "evidence_mode": evidence_mode,
        "sources": sources,
        "evidence_groups": evidence_groups,
        "calculations": data.get("calculations", []),
        "claims": claims,
        "derived_release_status": release_status,
    }
    fingerprint = _sha256_bytes(_canonical(fingerprint_payload).encode("utf-8"))
    checks.append({"name": "source_registry", "passed": not any(item.startswith("sources[") for item in errors)})
    checks.append({"name": "evidence_completeness", "passed": not any(item.startswith("evidence_groups[") for item in errors)})
    checks.append({"name": "calculation_reproduction", "passed": not any(item.startswith("calculations[") for item in errors)})
    checks.append({"name": "claim_synchronization", "passed": not any(item.startswith(("claims[", "metrics[", "overview", "sections[", "summary.")) for item in errors)})

    return {
        "schema_version": "1.0",
        "derived_release_status": release_status,
        "evidence_fingerprint": fingerprint,
        "errors": errors,
        "warnings": warnings,
        "conditions": conditions,
        "checks": checks,
        "recalculated_values": calculated_values,
    }


def write_audit(result: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
