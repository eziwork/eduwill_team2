from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any

from evidence_audit import audit_request, write_audit
from match_listings import deduplicate, load_candidates, match_candidates
from plan_sources import _load_registry, plan_sources
from validate_intake import load_intake, validate_intake


ROLE_LABELS = {
    "BUY": "매수인",
    "SELL": "매도인",
    "TENANT": "임차인",
    "LANDLORD": "임대인",
    "OWNER": "소유자",
    "OPERATOR": "사업 운영자",
}
MODE_LABELS = {"SALE": "sale", "JEONSE": "jeonse", "MONTHLY_RENT": "monthly_rent"}
PROPERTY_LABELS = {
    "APT": "아파트",
    "ROWHOUSE": "연립·다세대",
    "DETACHED_HOUSE": "단독·다가구",
    "OFFICETEL": "오피스텔",
    "LAND": "토지",
    "COMMERCIAL": "상업·업무용",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def resolve_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def format_krw(value: float | int | None) -> str:
    if value is None:
        return "확인 불가"
    amount = float(value)
    if abs(amount) >= 100_000_000:
        text = f"{amount / 100_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}억원"
    if abs(amount) >= 10_000:
        text = f"{amount / 10_000:,.0f}"
        return f"{text}만원"
    return f"{amount:,.0f}원"


def format_count(value: int) -> str:
    return f"{value}건"


def area_descriptor(scope: dict[str, Any]) -> str:
    low = scope.get("requested_area_min_sqm")
    high = scope.get("requested_area_max_sqm")
    if low is not None and high is not None:
        return f"전용 {float(low):g}~{float(high):g}㎡"
    if low is not None:
        return f"전용 {float(low):g}㎡ 이상"
    if high is not None:
        return f"전용 {float(high):g}㎡ 이하"
    return "면적 전체"


def source_scope(intake: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": intake["target"]["name"],
        "address": intake["target"].get("address"),
        "property_type": intake["target"]["property_type"],
        "trade_type": intake["transaction"]["trade_type"],
        "history_years": intake["period"]["history_years"],
        "area_min_sqm": intake.get("scope", {}).get("requested_area_min_sqm"),
        "area_max_sqm": intake.get("scope", {}).get("requested_area_max_sqm"),
    }


def load_official_rows(intake: dict[str, Any], official_path: Path | None) -> list[dict[str, Any]]:
    if official_path:
        payload = json.loads(official_path.read_text(encoding="utf-8-sig"))
    else:
        payload = intake.get("demo", {}).get("official_rows", [])
    if isinstance(payload, dict):
        payload = payload.get("rows", payload.get("records", []))
    if not isinstance(payload, list):
        raise ValueError("official rows must be a JSON list")
    return [row for row in payload if isinstance(row, dict)]


def row_price(row: dict[str, Any], trade_type: str) -> float | None:
    if trade_type == "SALE":
        return number(row.get("deal_amount_krw"))
    if trade_type == "JEONSE":
        return number(row.get("deposit_krw"))
    return number(row.get("monthly_rent_krw"))


def listing_price(row: dict[str, Any], trade_type: str) -> float | None:
    if trade_type == "SALE":
        return number(row.get("price_krw"))
    if trade_type == "JEONSE":
        return number(row.get("deposit_krw"))
    return number(row.get("monthly_rent_krw"))


def filter_official(rows: list[dict[str, Any]], trade_type: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    valid: list[dict[str, Any]] = []
    reasons = {"cancelled": 0, "trade_type_mismatch": 0, "missing_metric": 0}
    for row in rows:
        if bool(row.get("cancelled")):
            reasons["cancelled"] += 1
            continue
        row_trade = str(row.get("trade_type", trade_type))
        if row_trade and row_trade != trade_type:
            reasons["trade_type_mismatch"] += 1
            continue
        if trade_type == "MONTHLY_RENT":
            if number(row.get("deposit_krw")) is None or number(row.get("monthly_rent_krw")) is None:
                reasons["missing_metric"] += 1
                continue
        elif row_price(row, trade_type) is None:
            reasons["missing_metric"] += 1
            continue
        valid.append(row)
    return valid, reasons


def latest_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated = [row for row in rows if str(row.get("contract_date", ""))]
    return max(dated, key=lambda row: str(row.get("contract_date", ""))) if dated else (rows[-1] if rows else None)


def metric_summary(rows: list[dict[str, Any]], trade_type: str, basis_date: str) -> dict[str, Any]:
    valid, reasons = filter_official(rows, trade_type)
    prices = [row_price(row, trade_type) for row in valid]
    prices = [value for value in prices if value is not None]
    latest = latest_row(valid)
    deposits = [number(row.get("deposit_krw")) for row in valid]
    rents = [number(row.get("monthly_rent_krw")) for row in valid]
    pairs = [
        {"deposit_krw": deposit, "monthly_rent_krw": rent}
        for deposit, rent in zip(deposits, rents)
        if deposit is not None and rent is not None
    ]
    current_month = basis_date[:7]
    provisional_count = sum(1 for row in valid if str(row.get("contract_date", ""))[:7] == current_month)
    return {
        "raw_count": len(rows),
        "valid_count": len(valid),
        "excluded": reasons,
        "valid_rows": valid,
        "prices": prices,
        "pairs": pairs,
        "latest": latest,
        "latest_value": row_price(latest, trade_type) if latest else None,
        "minimum": min(prices) if prices else None,
        "median": statistics.median(prices) if prices else None,
        "maximum": max(prices) if prices else None,
        "provisional_current_month_count": provisional_count,
    }


def load_listing_input(intake: dict[str, Any], intake_dir: Path, explicit_path: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]], Path | None]:
    candidate = explicit_path
    if candidate is None:
        candidate = resolve_path(intake.get("collection", {}).get("listings_path"), intake_dir)
    if candidate and candidate.is_file():
        source, rows = load_candidates(candidate)
        return source, rows, candidate
    demo = intake.get("demo", {}).get("listings")
    if isinstance(demo, dict):
        rows = demo.get("listings", [])
        return demo.get("source", {}), [row for row in rows if isinstance(row, dict)], None
    return {}, [], None


def calculation(calc_id: str, operation: str, inputs: dict[str, Any], output: float, display: str, unit: str, input_path: str, input_key: str, tolerance: float = 1e-9, rounding: str = "정수") -> dict[str, Any]:
    return {
        "id": calc_id,
        "operation": operation,
        "inputs": inputs,
        "output": output,
        "display_value": display,
        "input_artifact_path": input_path,
        "input_key": input_key,
        "tolerance": tolerance,
        "unit": unit,
        "rounding": rounding,
    }


def calculated_claim(claim_id: str, statement: str, display: str, source_ids: list[str], group_ids: list[str], calculation_id: str, scope: str = "complete", limitation: str = "") -> dict[str, Any]:
    return {
        "id": claim_id,
        "kind": "calculated",
        "statement": statement,
        "display_value": display,
        "source_ids": source_ids,
        "evidence_group_ids": group_ids,
        "calculation_id": calculation_id,
        "scope": scope,
        "limitation": limitation,
    }


def direct_claim(claim_id: str, statement: str, source_ids: list[str], group_ids: list[str], display: str | None = None, scope: str = "complete", limitation: str = "") -> dict[str, Any]:
    claim: dict[str, Any] = {
        "id": claim_id,
        "kind": "direct",
        "statement": statement,
        "source_ids": source_ids,
        "evidence_group_ids": group_ids,
        "scope": scope,
        "limitation": limitation,
    }
    if display is not None:
        claim["display_value"] = display
    if any(character.isdigit() for character in statement):
        claim["value_origin"] = "observed"
    return claim


def interpretive_claim(claim_id: str, statement: str, source_ids: list[str], group_ids: list[str]) -> dict[str, Any]:
    return {
        "id": claim_id,
        "kind": "interpretive",
        "statement": statement,
        "source_ids": source_ids,
        "evidence_group_ids": group_ids,
        "scope": "complete",
        "limitation": "",
    }


def build_report_request(
    intake: dict[str, Any],
    report_root: Path,
    official: dict[str, Any],
    listing_source: dict[str, Any],
    listing_rows: list[dict[str, Any]],
    official_manifest: dict[str, Any] | None,
    matching_result: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_mode = intake["evidence_mode"]
    trade_type = intake["transaction"]["trade_type"]
    target = intake["target"]
    scope = intake.get("scope", {})
    role = intake["customer"]["role"]
    basis_date = intake["basis_date"]
    communication = intake.get("communication") if isinstance(intake.get("communication"), dict) else {}
    communication_mode = str(communication.get("mode") or "CUSTOMER_SALES")
    requested_profile = str(communication.get("report_profile") or "AUTO")
    conversion_goal = str(communication.get("conversion_goal") or ("SITE_VISIT_CONSULTATION" if communication_mode == "CUSTOMER_SALES" else "INFORMED_DECISION"))
    decision_context = intake.get("decision_context") if isinstance(intake.get("decision_context"), dict) else {}
    # All standard reports use the same Golden V3 renderer.  The former
    # COMPACT_6 branch produced a different design system and made quality
    # depend on the question type.  Keep legacy intake values readable, but
    # normalize every route to the canonical nine-page profile.
    report_profile = "EXTENDED_9"
    descriptor = f"{PROPERTY_LABELS[target['property_type']]} · {area_descriptor(scope)} · { {'SALE':'매매','JEONSE':'전세','MONTHLY_RENT':'월세'}[trade_type] }"
    source_ids: list[str] = []
    sources: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []

    official_rows_path = report_root / "normalized" / "official_rows.json"
    listing_rows_path = report_root / "normalized" / "listings.json"
    intake_path = report_root / "intake.json"

    if evidence_mode == "demo":
        sources.append(
            {
                "id": "DEMO-1",
                "grade": "DEMO",
                "name": "교육용 가상 데이터",
                "url": "내부 생성 예시 · 외부 링크 없음",
                "as_of": basis_date,
                "scope": "리포트 구조와 계산 흐름 실습",
                "limitation": "실제 시세나 계약 판단에 사용할 수 없음",
            }
        )
        source_ids = ["DEMO-1"]
        group_ids: list[str] = []
    else:
        intake_source_id = "USER-INTAKE"
        intake_group_id = "GROUP-INTAKE"
        sources.append(
            {
                "id": intake_source_id,
                "grade": "S4",
                "lane": "field_or_private_confirmations",
                "name": "고객·중개사 입력",
                "url": "내부 확인 기록 · 외부 링크 없음",
                "as_of": basis_date,
                "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "query_conditions": {"report_id": intake["report_id"], "task_mode": intake["task_mode"]},
                "scope": "대상, 판단질문, 제시조건과 비교범위",
                "limitation": "입력자가 제공한 사실이며 공공 원자료와 별도로 확인해야 함",
            }
        )
        groups.append(
            {
                "id": intake_group_id,
                "lane": "field_or_private_confirmations",
                "source_ids": [intake_source_id],
                "required_for_question": True,
                "status": "COMPLETE",
                "coverage": {"scope_exhausted": True},
                "counts": {"raw_rows": 1, "normalized_rows": 1, "excluded_rows": 0, "parse_failed_rows": 0, "used_rows": 1},
                "exclusions": [],
                "errors": [],
                "artifacts": [{"path": relative(intake_path, report_root), "sha256": sha256(intake_path)}],
                "completeness_basis": "잠긴 intake 한 건을 보존함",
            }
        )
        source_ids.append(intake_source_id)
        group_ids = [intake_group_id]

        if official["raw_count"] or official_manifest is not None:
            official_source_id = "MOLIT-OFFICIAL"
            official_group_id = "GROUP-OFFICIAL"
            manifest = official_manifest or {}
            endpoint = str(manifest.get("endpoint") or "https://www.data.go.kr/")
            retrieved_at = str(manifest.get("retrieved_at") or datetime.now().astimezone().isoformat(timespec="seconds"))
            query = manifest.get("query") if isinstance(manifest.get("query"), dict) else source_scope(intake)
            sources.append(
                {
                    "id": official_source_id,
                    "grade": "S1",
                    "lane": "closed_or_reported_transactions",
                    "name": "국토교통부 실거래가 공개시스템 RTMS",
                    "url": endpoint if endpoint.startswith("http") else "https://www.data.go.kr/",
                    "as_of": basis_date,
                    "retrieved_at": retrieved_at,
                    "query_conditions": query,
                    "scope": "선택한 물건유형·거래유형·법정동코드·기간·면적의 신고 거래",
                    "limitation": "신고 지연과 정정·해제가 발생할 수 있고 현재월은 잠정치임",
                }
            )
            exclusion_items = [
                {"reason": reason, "count": count}
                for reason, count in official["excluded"].items()
                if count
            ]
            periods = sorted({str(item.get("month")) for item in manifest.get("requests", []) if item.get("month")})
            calc_input_path = report_root / "normalized" / "official-calculation-inputs.json"
            calc_inputs = {"prices": {"values": official["prices"]}, "pairs": official["pairs"]}
            write_json(calc_input_path, calc_inputs)
            groups.append(
                {
                    "id": official_group_id,
                    "lane": "closed_or_reported_transactions",
                    "source_ids": [official_source_id],
                    "required_for_question": True,
                    "status": "COMPLETE" if official["raw_count"] else "ZERO_RESULT",
                    "coverage": {"expected_periods": periods, "completed_periods": periods, "scope_exhausted": True},
                    "counts": {
                        "raw_rows": official["raw_count"],
                        "normalized_rows": official["valid_count"],
                        "excluded_rows": sum(official["excluded"].values()),
                        "parse_failed_rows": 0,
                        "used_rows": official["valid_count"],
                    },
                    "exclusions": exclusion_items,
                    "errors": [],
                    "artifacts": [
                        {"path": relative(official_rows_path, report_root), "sha256": sha256(official_rows_path)},
                        {"path": relative(calc_input_path, report_root), "sha256": sha256(calc_input_path)},
                    ],
                    "completeness_basis": "요청 범위의 RTMS 응답과 정규화 행을 보존함",
                }
            )
            source_ids.append(official_source_id)
            group_ids.append(official_group_id)

        if listing_rows:
            listing_source_id = "LISTINGS-SAMPLE"
            listing_group_id = "GROUP-LISTINGS"
            quality = str(listing_source.get("quality_status") or "SAMPLE_ONLY")
            if quality not in {"COMPLETE", "ZERO_RESULT", "SAMPLE_ONLY", "PARTIAL"}:
                quality = "SAMPLE_ONLY"
            deduped, duplicate_count = deduplicate(listing_rows)
            listing_calc_path = report_root / "normalized" / "listing-calculation-inputs.json"
            listing_values = [listing_price(row, trade_type) for row in deduped]
            listing_values = [value for value in listing_values if value is not None]
            write_json(listing_calc_path, {"prices": {"values": listing_values}})
            sources.append(
                {
                    "id": listing_source_id,
                    "grade": "S3" if str(listing_source.get("name", "")).startswith("네이버") else "S4",
                    "lane": "current_public_listings",
                    "name": str(listing_source.get("name") or "사용자 제공 공개매물 표본"),
                    "url": str(listing_source.get("url") or "내부 확인 기록 · 외부 링크 없음"),
                    "as_of": str(listing_source.get("retrieved_at") or basis_date)[:10],
                    "retrieved_at": str(listing_source.get("retrieved_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
                    "query_conditions": {"visible_scope": str(listing_source.get("query_conditions") or "사용자 제공 범위")},
                    "scope": "조회하거나 제공받은 현재 공개매물 표본",
                    "limitation": "광고 중복·종료·계약진행 상태와 전체 재고를 보장하지 않음",
                }
            )
            listing_artifacts = [
                {"path": relative(listing_rows_path, report_root), "sha256": sha256(listing_rows_path)},
                {"path": relative(listing_calc_path, report_root), "sha256": sha256(listing_calc_path)},
            ]
            matching_path = report_root / "data" / "matching.json"
            if matching_result is not None and matching_path.is_file():
                listing_artifacts.append({"path": relative(matching_path, report_root), "sha256": sha256(matching_path)})
            groups.append(
                {
                    "id": listing_group_id,
                    "lane": "current_public_listings",
                    "source_ids": [listing_source_id],
                    "required_for_question": intake["task_mode"] == "MARKET_REPORT_WITH_MATCHING",
                    "status": quality,
                    "coverage": {"scope_exhausted": quality in {"COMPLETE", "ZERO_RESULT"}},
                    "counts": {
                        "raw_rows": len(listing_rows),
                        "normalized_rows": len(deduped),
                        "excluded_rows": duplicate_count,
                        "parse_failed_rows": 0,
                        "used_rows": len(deduped),
                    },
                    "exclusions": ([{"reason": "duplicate listing_id or normalized tuple", "count": duplicate_count}] if duplicate_count else []),
                    "errors": [],
                    "artifacts": listing_artifacts,
                    "completeness_basis": "표시된 조사 표본과 중복정리 결과를 보존함",
                }
            )
            source_ids.append(listing_source_id)
            group_ids.append(listing_group_id)

    target_claim_id = "CLAIM-TARGET"
    target_statement = f"대상은 {target['name']} · {descriptor}이며 주소는 {target.get('address') or target.get('lot_number_hint')}입니다. 고객 질문은 {intake['customer']['decision_question']}"
    if evidence_mode == "demo":
        claims.append(direct_claim(target_claim_id, target_statement, source_ids, []))
    else:
        claims.append(direct_claim(target_claim_id, target_statement, ["USER-INTAKE"], ["GROUP-INTAKE"]))

    proposed_values = [
        intake.get("terms", {}).get("proposed_price_krw"),
        intake.get("terms", {}).get("deposit_krw"),
        intake.get("terms", {}).get("monthly_rent_krw"),
    ]
    proposed = next((number(value) for value in proposed_values if number(value) is not None), None)
    proposed_claim_id = None
    if proposed is not None:
        proposed_claim_id = "CLAIM-PROPOSED"
        display = format_krw(proposed)
        source_for_claim = source_ids if evidence_mode == "demo" else ["USER-INTAKE"]
        group_for_claim = [] if evidence_mode == "demo" else ["GROUP-INTAKE"]
        claims.append(direct_claim(proposed_claim_id, f"고객이 제시한 검토 조건은 {display}입니다.", source_for_claim, group_for_claim, display))

    official_claims: dict[str, str] = {}
    if official["prices"]:
        if evidence_mode == "actual":
            calc_path = "normalized/official-calculation-inputs.json"
            for operation, key, value in (
                ("count", "count", float(len(official["prices"]))),
                ("min", "minimum", float(official["minimum"])),
                ("median", "median", float(official["median"])),
                ("max", "maximum", float(official["maximum"])),
            ):
                calc_id = f"CALC-OFFICIAL-{operation.upper()}"
                display = format_count(len(official["prices"])) if operation == "count" else format_krw(value)
                inputs = {"values": official["prices"]}
                calculations.append(calculation(calc_id, operation, inputs, value, display, "건" if operation == "count" else "원", calc_path, "prices", 500_000 if operation != "count" else 1e-9, "정수" if operation == "count" else "소수 둘째 자리 억원"))
                claim_id = f"CLAIM-OFFICIAL-{operation.upper()}"
                claims.append(calculated_claim(claim_id, f"선택 범위의 유효 실거래 {display}이 확인됩니다.", display, ["MOLIT-OFFICIAL"], ["GROUP-OFFICIAL"], calc_id))
                official_claims[key] = claim_id
        else:
            for key, value in (("count", len(official["prices"])), ("minimum", official["minimum"]), ("median", official["median"]), ("maximum", official["maximum"])):
                display = format_count(int(value)) if key == "count" else format_krw(value)
                claim_id = f"CLAIM-OFFICIAL-{key.upper()}"
                claims.append(direct_claim(claim_id, f"교육용 유효 실거래 {display}을 사용합니다.", source_ids, [], display))
                official_claims[key] = claim_id
        latest = official.get("latest") or {}
        latest_display = format_krw(official.get("latest_value"))
        latest_claim_id = "CLAIM-OFFICIAL-LATEST"
        latest_sources = source_ids if evidence_mode == "demo" else ["MOLIT-OFFICIAL"]
        latest_groups = [] if evidence_mode == "demo" else ["GROUP-OFFICIAL"]
        claims.append(direct_claim(latest_claim_id, f"최근 유효 거래는 {latest.get('contract_date') or '날짜 확인 필요'} · {latest_display}입니다.", latest_sources, latest_groups, latest_display))
        official_claims["latest"] = latest_claim_id

    listing_deduped, _listing_duplicate_count = deduplicate(listing_rows)
    listing_values = [listing_price(row, trade_type) for row in listing_deduped]
    listing_values = [value for value in listing_values if value is not None]
    listing_claims: dict[str, str] = {}
    if listing_values:
        sample_scope = evidence_mode == "actual"
        if evidence_mode == "actual":
            calc_path = "normalized/listing-calculation-inputs.json"
            for operation, key, value in (
                ("count", "count", float(len(listing_values))),
                ("min", "minimum", float(min(listing_values))),
                ("median", "median", float(statistics.median(listing_values))),
                ("max", "maximum", float(max(listing_values))),
            ):
                calc_id = f"CALC-LISTING-{operation.upper()}"
                display = format_count(len(listing_values)) if operation == "count" else format_krw(value)
                calculations.append(calculation(calc_id, operation, {"values": listing_values}, value, display, "건" if operation == "count" else "원", calc_path, "prices", 500_000 if operation != "count" else 1e-9, "정수" if operation == "count" else "소수 둘째 자리 억원"))
                claim_id = f"CLAIM-LISTING-{operation.upper()}"
                claims.append(calculated_claim(claim_id, f"확인한 표본 매물의 {display}이 확인됩니다.", display, ["LISTINGS-SAMPLE"], ["GROUP-LISTINGS"], calc_id, "sample", "조회한 표본으로 전체 공개매물을 의미하지 않음"))
                listing_claims[key] = claim_id
        else:
            for key, value in (("count", len(listing_values)), ("minimum", min(listing_values)), ("median", statistics.median(listing_values)), ("maximum", max(listing_values))):
                display = format_count(int(value)) if key == "count" else format_krw(value)
                claim_id = f"CLAIM-LISTING-{key.upper()}"
                claims.append(direct_claim(claim_id, f"교육용 표본 매물 {display}을 사용합니다.", source_ids, [], display))
                listing_claims[key] = claim_id

    evidence_source_for_advice = [source_ids[0]] if source_ids else []
    evidence_group_for_advice = [groups[0]["id"]] if groups else []
    advice_claim_id = "CLAIM-ADVICE"
    claims.append(interpretive_claim(advice_claim_id, "거래자료와 공개매물, 현장조건을 분리해 확인하고 계약 직전에 다시 점검해야 합니다.", evidence_source_for_advice, evidence_group_for_advice))

    matching_claim_ids: list[str] = []
    if matching_result and matching_result.get("results"):
        for index, item in enumerate(matching_result["results"][:6], start=1):
            candidate = item["candidate"]
            claim_id = f"CLAIM-MATCH-{index}"
            display = f"{item['score']:g}점"
            if evidence_mode == "actual":
                calc_path = report_root / "normalized" / "matching-calculation-inputs.json"
                score_inputs = {"scores": {}}
                if calc_path.is_file():
                    score_inputs = json.loads(calc_path.read_text(encoding="utf-8"))
                score_inputs.setdefault("scores", {})[str(index)] = {"numerator": len(item["matched_preferences"]), "denominator": max(1, len(intake.get("matching", {}).get("preferences", [])))}
                write_json(calc_path, score_inputs)
                calc_id = f"CALC-MATCH-{index}"
                calculations.append(calculation(calc_id, "percentage", score_inputs["scores"][str(index)], float(item["score"]), display, "점", "normalized/matching-calculation-inputs.json", f"scores.{index}", 0.01, "소수 둘째 자리"))
                statement = f"확인한 표본 후보 {candidate.get('name', index)}는 선호조건 {len(item['matched_preferences'])}개를 충족해 {display}이며 미확인 조건은 {len(item['unknown_conditions'])}개입니다."
                claims.append(calculated_claim(claim_id, statement, display, ["LISTINGS-SAMPLE"], ["GROUP-LISTINGS"], calc_id, "sample", "동일 가중치의 확인한 표본 비교이며 최종 추천을 보장하지 않음"))
            else:
                statement = f"교육용 후보 {candidate.get('name', index)}는 선호조건 {len(item['matched_preferences'])}개를 충족해 {display}입니다."
                claims.append(direct_claim(claim_id, statement, source_ids, [], display))
            matching_claim_ids.append(claim_id)
        if evidence_mode == "actual":
            matching_calc_path = report_root / "normalized" / "matching-calculation-inputs.json"
            listing_group = next((group for group in groups if group["id"] == "GROUP-LISTINGS"), None)
            if listing_group and matching_calc_path.is_file():
                artifact = {"path": relative(matching_calc_path, report_root), "sha256": sha256(matching_calc_path)}
                if artifact not in listing_group["artifacts"]:
                    listing_group["artifacts"].append(artifact)

    metric_items: list[dict[str, Any]] = []
    if proposed_claim_id:
        metric_items.append({"label": "고객 제시조건", "value": format_krw(proposed), "note": "고객·중개사 입력", "claim_id": proposed_claim_id})
    if official_claims.get("median"):
        median_claim = next(claim for claim in claims if claim["id"] == official_claims["median"])
        metric_items.append({"label": "실거래 중앙값", "value": median_claim["display_value"], "note": "취소·해제 제외", "claim_id": official_claims["median"]})
    if official_claims.get("latest") and len(metric_items) < 3:
        latest_claim = next(claim for claim in claims if claim["id"] == official_claims["latest"])
        metric_items.append({"label": "최근 유효 거래", "value": latest_claim["display_value"], "note": "신고자료 기준", "claim_id": official_claims["latest"]})
    if listing_claims.get("median") and len(metric_items) < 3:
        listing_claim = next(claim for claim in claims if claim["id"] == listing_claims["median"])
        metric_items.append({"label": "표본 호가 중앙값", "value": listing_claim["display_value"], "note": "확인한 표본", "claim_id": listing_claims["median"]})
    if official_claims.get("count") and len(metric_items) < 3:
        count_claim = next(claim for claim in claims if claim["id"] == official_claims["count"])
        metric_items.append({"label": "유효 실거래", "value": count_claim["display_value"], "note": "선택범위 기준", "claim_id": official_claims["count"]})
    while len(metric_items) < 3:
        metric_items.append({"label": "추가 확인", "value": "확인 불가", "note": "근거자료 필요", "claim_id": advice_claim_id})
    metric_items = metric_items[:3]

    official_visual_claims = [value for key, value in official_claims.items() if key in {"minimum", "median", "maximum", "latest"}]
    if proposed_claim_id:
        official_visual_claims.append(proposed_claim_id)
    if trade_type == "MONTHLY_RENT" and official["pairs"]:
        pair_claim_id = "CLAIM-OFFICIAL-PAIRS"
        pair_text = ", ".join(
            f"보증금 {pair['deposit_krw'] / 10_000:,.0f}만원·월세 {pair['monthly_rent_krw'] / 10_000:,.0f}만원"
            for pair in official["pairs"]
        )
        pair_sources = source_ids if evidence_mode == "demo" else ["MOLIT-OFFICIAL"]
        pair_groups = [] if evidence_mode == "demo" else ["GROUP-OFFICIAL"]
        claims.append(direct_claim(pair_claim_id, f"확인된 월세 조합은 {pair_text}입니다.", pair_sources, pair_groups))
        official_visual = {
            "type": "scatter",
            "points": [
                {"x": pair["deposit_krw"] / 10_000, "y": pair["monthly_rent_krw"] / 10_000, "label": "실거래"}
                for pair in official["pairs"]
            ],
            "x_label": "보증금(만원)",
            "y_label": "월세(만원)",
            "claim_ids": [pair_claim_id],
        }
        official_visual_claims = [pair_claim_id]
    elif official["prices"]:
        official_values = [official["minimum"], official["median"], official["maximum"]]
        target_value = proposed if proposed is not None else official["median"]
        chart_values = [value / 100_000_000 for value in official_values if value is not None]
        target_chart = float(target_value) / 100_000_000
        official_visual = {
            "type": "band",
            "min": min(chart_values + [target_chart]),
            "max": max(chart_values + [target_chart]),
            "unit": "억원",
            "values": chart_values,
            "target": target_chart,
            "target_label": "검토조건" if proposed is not None else "중앙값",
            "claim_ids": official_visual_claims,
        }
    else:
        official_visual = {"type": "matrix", "rows": [{"label": "공식 실거래", "status": "자료 보완", "note": "공식 자료 연결 후 동일 형식으로 반영"}], "claim_ids": [advice_claim_id]}
        official_visual_claims = [advice_claim_id]

    listing_visual_claim_ids = [value for key, value in listing_claims.items() if key in {"minimum", "median", "maximum"}]
    if listing_values:
        rows_for_chart = []
        for label, key, value in (("표본 최저", "minimum", min(listing_values)), ("표본 중앙", "median", statistics.median(listing_values)), ("표본 최고", "maximum", max(listing_values))):
            rows_for_chart.append({"label": label, "value": value / 100_000_000, "display": format_krw(value), "note": "확인한 표본", "highlight": key == "median"})
        listing_visual = {"type": "bar", "rows": rows_for_chart, "max": max(value / 100_000_000 for value in listing_values), "claim_ids": listing_visual_claim_ids}
    else:
        listing_visual = {"type": "matrix", "rows": [{"label": "현재 공개매물", "status": "자료 보완", "note": "표본 또는 제공자료 연결 시 반영"}], "claim_ids": [advice_claim_id]}
        listing_visual_claim_ids = [advice_claim_id]

    official_section_claims = list(dict.fromkeys(official_visual_claims + ([official_claims["count"]] if official_claims.get("count") else [advice_claim_id])))
    listing_section_claims = list(dict.fromkeys(listing_visual_claim_ids or [advice_claim_id]))
    if evidence_mode == "actual" and listing_values:
        sample_prefix = "확인한 표본 "
    else:
        sample_prefix = ""

    if matching_result and matching_result.get("results"):
        checklist = []
        for index, item in enumerate(matching_result["results"][:6], start=1):
            candidate = item["candidate"]
            unknown = ", ".join(item["unknown_conditions"]) or "없음"
            body = f"선호조건 점수 {item['score']:g}점 · 미확인 조건 {unknown}"
            checklist.append({"title": str(candidate.get("name") or f"후보 {index}"), "body": body, "claim_id": matching_claim_ids[index - 1]})
        fallback_checks = [
            {"title": "탈락 후보", "body": "필수조건을 충족하지 못한 후보는 제외사유를 내부 비교기록에서 확인", "claim_id": advice_claim_id},
            {"title": "현장 재확인", "body": "미확인 조건은 계약 전에 원자료와 현장에서 다시 확인", "claim_id": advice_claim_id},
            {"title": "순위 해석", "body": "동일 가중치 점수는 검토순서이며 최종 추천이나 적합성 보장이 아님", "claim_id": advice_claim_id},
        ]
        for fallback in fallback_checks:
            if len(checklist) >= 3:
                break
            checklist.append(fallback)
    else:
        checklist = [
            {"title": "대상 일치", "body": "동일 유형·거래종류·면적·지역 범위인지 확인", "claim_id": advice_claim_id},
            {"title": "거래 검증", "body": "해제·정정·신고지연과 최신 원자료를 재확인", "claim_id": advice_claim_id},
            {"title": "현장 조건", "body": "층·향·수리·인도·접도·용도 조건을 별도 확인", "claim_id": advice_claim_id},
            {"title": "공개매물", "body": "중복 광고와 실제 거래 가능 여부를 확인", "claim_id": advice_claim_id},
            {"title": "계약 조건", "body": "잔금·입주·부가세·관리비 등 의사결정 조건 확인", "claim_id": advice_claim_id},
            {"title": "기준일", "body": "계약 직전 가격과 행정·권리 상태를 다시 조회", "claim_id": advice_claim_id},
        ]

    overview_claims = list(dict.fromkeys([item["claim_id"] for item in metric_items] + [advice_claim_id]))
    report = {
        "schema_version": "1.0",
        "report_type": "standard",
        "report_engine": {
            "id": "EZIWORK_GOLDEN_V3",
            "version": "3.1.0",
            "page_count": 9,
            "legacy_profile_requested": requested_profile,
        },
        "communication_mode": communication_mode,
        "report_profile": report_profile,
        "conversion_goal": conversion_goal,
        "decision_context": decision_context,
        "mode": MODE_LABELS[trade_type],
        "evidence_mode": evidence_mode,
        "basis_date": basis_date,
        "target": {
            "name": target["name"],
            "address": target.get("address") or target.get("lot_number_hint") or "주소 확인 필요",
            "descriptor": descriptor,
            "image_path": str(target.get("image_path") or ""),
            "map_image_path": str(target.get("map_image_path") or ""),
            "map_link": str(target.get("map_link") or ""),
            "map_source_id": str(target.get("map_source_id") or ""),
            "walking_routes": [
                route for route in target.get("walking_routes", [])
                if isinstance(route, dict) and number(route.get("minutes")) is not None and float(route["minutes"]) <= 10
            ],
            "claim_ids": [target_claim_id],
        },
        "customer": {
            "role": ROLE_LABELS[role],
            "question": intake["customer"]["decision_question"],
            "scope": "공식 실거래와 현재 공개자료를 분리하고 미확인 조건을 함께 검토합니다.",
            "claim_ids": [target_claim_id, advice_claim_id],
        },
        "brand": {
            "name": intake.get("output", {}).get("brand_name") or "EZIWORK",
            "color": intake.get("output", {}).get("brand_color") or "#2c61ef",
            "agent_name": intake.get("output", {}).get("agent_name") or "",
            "contact": intake.get("output", {}).get("contact") or "",
        },
        "metrics": metric_items,
        "golden_v3": {
            "official_transactions": [
                {
                    "contract_date": str(row.get("contract_date") or ""),
                    "price_krw": row_price(row, trade_type),
                    "deposit_krw": number(row.get("deposit_krw")),
                    "monthly_rent_krw": number(row.get("monthly_rent_krw")),
                    "floor": number(row.get("floor")),
                    "building": str(row.get("apartment_dong") or row.get("building_name") or row.get("dong") or ""),
                    "area_sqm": number(row.get("exclusive_area_sqm")),
                }
                for row in official.get("valid_rows", [])
            ],
            "current_listings": [
                {
                    "name": str(row.get("name") or row.get("listing_id") or "공개매물"),
                    "price_krw": listing_price(row, trade_type),
                    "deposit_krw": number(row.get("deposit_krw")),
                    "monthly_rent_krw": number(row.get("monthly_rent_krw")),
                    "floor": number(row.get("floor")),
                    "building": str(row.get("apartment_dong") or row.get("building") or row.get("dong") or ""),
                }
                for row in listing_deduped
            ],
            "history_years": intake.get("period", {}).get("history_years"),
            "proposed_price_krw": proposed,
            "budget_krw": number(decision_context.get("budget_krw")),
            "holding_years": number(decision_context.get("intended_holding_years")),
            "resale_intent": str(decision_context.get("resale_intent") or ""),
        },
        "overview": {
            "title": "지금 확인된 자료는 무엇을 말할까요?",
            "paragraphs": [
                "완료된 거래와 현재 공개매물은 성격이 달라 각각의 위치와 한계를 따로 봅니다.",
                "확인되지 않은 현장·권리·계약 조건은 가격 차이를 설명하는 근거로 사용하지 않습니다.",
            ],
            "takeaway": "확인된 사실, 그 의미, 아직 확인되지 않은 것과 다음 행동을 나누어 판단합니다.",
            "claim_ids": overview_claims,
            "source_ids": source_ids,
        },
        "sections": [
            {
                "part": "PART 01 · OFFICIAL TRANSACTIONS",
                "title": "공식 실거래는 어느 위치일까요?",
                "lead": "선택한 대상과 비교범위에서 유효한 신고 거래만 사용했습니다." if official["prices"] else "선택한 범위의 공식 실거래 근거가 부족합니다.",
                "visual": official_visual,
                "caption": "국토교통부 신고자료 · 취소·해제 제외 · 현재월 잠정",
                "subtitle": "거래가 적으면 한 숫자보다 범위와 개별 사례를 봅니다",
                "body": "거래량과 면적·층·용도 차이를 함께 확인하고 자료가 부족하면 결론을 보류합니다.",
                "takeaway": "공식 실거래는 현재 호가와 합쳐 평균내지 않습니다.",
                "claim_ids": official_section_claims,
                "source_ids": source_ids,
            },
            {
                "part": "PART 02 · CURRENT MARKET",
                "title": "현재 공개매물은 어떻게 보일까요?",
                "lead": f"{sample_prefix}공개매물의 가격 위치를 실거래와 분리해 확인했습니다." if listing_values else "현재 공개매물 표본이 없어 가격 범위를 확정하지 않습니다.",
                "visual": listing_visual,
                "caption": f"{sample_prefix}공개매물 · 광고와 실제 거래 가능 상태가 다를 수 있음" if listing_values else "공개매물 자료 없음 · 계약 전 표본 확인 필요",
                "subtitle": "광고 수와 중복정리 후 후보 수는 다를 수 있습니다",
                "body": f"{sample_prefix}자료는 조회시점의 광고이며 전체 재고나 체결가격을 의미하지 않습니다." if listing_values else "브라우저 확인 또는 중개사가 보유한 후보목록을 추가하면 비교할 수 있습니다.",
                "takeaway": f"{sample_prefix}공개자료는 최신 상태와 중복 여부를 다시 확인해야 합니다." if listing_values else "자료가 없다는 사실을 가격 추정으로 대체하지 않습니다.",
                "claim_ids": listing_section_claims,
                "source_ids": source_ids,
            },
        ],
        "checklist": checklist,
        "summary": {
            "paragraphs": [
                "확인된 거래자료와 공개매물의 범위를 넘어 적정가격을 단정하지 않습니다.",
                "미확인 조건을 현장과 원자료에서 확인한 뒤 협상 또는 계약 기준을 정하는 것이 좋습니다.",
            ],
            "claim_ids": [advice_claim_id] + overview_claims,
            "cards": [
                {"title": "핵심 판단", "body": "근거가 확인된 범위 안에서만 가격 위치를 비교합니다.", "claim_id": advice_claim_id},
                {"title": "확인할 사항", "body": "현장조건과 최신 공개매물·정정자료가 판단을 바꿀 수 있습니다.", "claim_id": advice_claim_id},
                {"title": "다음 행동", "body": "계약 직전 같은 범위와 기준일로 원자료를 다시 확인합니다.", "claim_id": advice_claim_id},
            ],
        },
        "sources": sources,
        "evidence_groups": groups,
        "calculations": calculations,
        "claims": claims,
        "disclaimer": "본 자료는 표시된 기준일과 출처를 바탕으로 한 중개 상담 보조자료이며 감정평가·법률·세무·대출·보증·인허가 또는 가격 보장을 대신하지 않습니다.",
    }

    metrics_payload = {
        "schema_version": 1,
        "basis_date": basis_date,
        "official": {key: value for key, value in official.items() if key not in {"valid_rows", "latest"}},
        "listings": {
            "raw_count": len(listing_rows),
            "deduplicated_count": len(listing_deduped),
            "minimum": min(listing_values) if listing_values else None,
            "median": statistics.median(listing_values) if listing_values else None,
            "maximum": max(listing_values) if listing_values else None,
        },
    }
    return report, metrics_payload


def prepare(args: argparse.Namespace) -> tuple[Path, Path, str]:
    intake_path = args.intake.resolve()
    intake = load_intake(intake_path)
    errors, warnings = validate_intake(intake, intake_path.parent)
    if errors:
        raise ValueError("; ".join(errors))

    report_root = args.report_root.resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    write_json(report_root / "intake.json", intake)

    registry = _load_registry(Path(__file__).resolve().parent)
    source_plan = plan_sources(intake, registry, intake_path.parent)
    source_plan["warnings"] = warnings
    write_json(report_root / "source-plan.json", source_plan)

    official_path = args.official_rows.resolve() if args.official_rows else None
    manifest_path = args.official_manifest.resolve() if args.official_manifest else None
    if intake["evidence_mode"] == "actual" and source_plan.get("transaction_source_id") and not official_path:
        raise ValueError("actual official route requires --official-rows")
    if intake["evidence_mode"] == "actual" and official_path and not manifest_path:
        raise ValueError("actual official rows require --official-manifest")
    rows = load_official_rows(intake, official_path)
    write_json(report_root / "normalized" / "official_rows.json", rows)
    manifest = None
    if manifest_path:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        write_json(report_root / "raw" / "official_manifest.json", manifest)

    trade_type = intake["transaction"]["trade_type"]
    official = metric_summary(rows, trade_type, intake["basis_date"])

    explicit_listings = args.listings.resolve() if args.listings else None
    listing_source, listing_rows, _source_path = load_listing_input(intake, intake_path.parent, explicit_listings)
    write_json(report_root / "normalized" / "listings.json", {"source": listing_source, "listings": listing_rows})

    matching_result = None
    if intake["task_mode"] == "MARKET_REPORT_WITH_MATCHING":
        candidate_path = resolve_path(intake.get("matching", {}).get("candidates_path"), intake_path.parent)
        if candidate_path is None or not candidate_path.is_file():
            raise ValueError("matching candidates are required")
        candidate_source, candidates = load_candidates(candidate_path)
        matching_result = match_candidates(candidates, intake["matching"].get("must_haves", []), intake["matching"].get("preferences", []))
        matching_result["source"] = candidate_source
        write_json(report_root / "data" / "matching.json", matching_result)
        if not matching_result.get("results"):
            raise ValueError("matching has no candidate remaining after must-have filters")
        if not listing_rows:
            listing_source, listing_rows = candidate_source, candidates
            write_json(report_root / "normalized" / "listings.json", {"source": listing_source, "listings": listing_rows})

    report, metrics = build_report_request(intake, report_root, official, listing_source, listing_rows, manifest, matching_result)
    write_json(report_root / "data" / "metrics.json", metrics)
    request_path = report_root / "report-request.json"
    write_json(request_path, report)
    audit = audit_request(report, report_root)
    audit_path = report_root / "evidence-audit.json"
    write_audit(audit, audit_path)
    return request_path, audit_path, audit["derived_release_status"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare metrics, matching, evidence, and a canonical Golden V3 report request.")
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--official-rows", type=Path)
    parser.add_argument("--official-manifest", type=Path)
    parser.add_argument("--listings", type=Path)
    args = parser.parse_args()
    try:
        request_path, audit_path, release = prepare(args)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"REQUEST: {request_path}")
    print(f"AUDIT: {audit_path}")
    print(f"RELEASE: {release}")
    return 2 if release == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
