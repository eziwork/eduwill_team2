from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from checkpoint_schema import migrate_request, selected_checkpoint_view, validate_page_plan
from evidence_audit import RELEASE_HOLD, audit_request


FORBIDDEN = (
    "고객에게는 이렇게 설명합니다",
    "고객에게 이렇게 정리해서 설명합니다",
    "중개사가 승인",
    "고객 전달 전",
    "영업용 멘트",
    "스킬 설계용",
    "javascript:",
)

DEMO_BADGE = "교육용 예시 · 실제 시세가 아님"
ACTUAL_FORBIDDEN_DEMO_PHRASES = (DEMO_BADGE, "교육용 예시", "실제 시세가 아님")
FINGERPRINT_META = {
    "evidence_fingerprint": "evidence-audit-sha256",
    "visible_payload_fingerprint": "visible-payload-sha256",
    "asset_manifest_fingerprint": "asset-manifest-sha256",
    "combined_release_fingerprint": "combined-release-sha256",
}


def _meta(text: str, name: str) -> str | None:
    match = re.search(
        rf'<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']*)["\']',
        text,
        re.I,
    )
    if not match:
        match = re.search(
            rf'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
            text,
            re.I,
        )
    return match.group(1) if match else None


def _sheet_count(text: str) -> int:
    return len(re.findall(r'class=["\'][^"\']*\bsheet\b', text, re.I))


def validate_html(text: str, request_data: dict[str, Any] | None, base_dir: Path) -> list[str]:
    errors: list[str] = []
    for phrase in FORBIDDEN:
        if phrase.lower() in text.lower():
            errors.append(f"forbidden or unresolved token: {phrase}")
    if re.search(r"\{\{\s*[A-Za-z0-9_.-]+\s*\}\}", text):
        errors.append("unresolved template placeholder")
    if re.search(r"<iframe\b", text, re.I):
        errors.append("iframe is not allowed")
    if re.search(r"href=[\"']\s*(?:#|)[\"']", text, re.I):
        errors.append("empty or placeholder href")
    if "cover-brand" not in text and "cover-kicker" not in text and "tiny-brand" not in text and 'class="brand"' not in text:
        errors.append("brand mark is missing")
    if "<html" not in text.lower() or "@page" not in text:
        errors.append("standalone print-ready HTML structure is missing")

    report_type = (_meta(text, "report-type") or "standard").upper()
    evidence_mode = (_meta(text, "evidence-mode") or "").lower()
    customer_type = (_meta(text, "customer-type") or "").upper()
    sheets = _sheet_count(text)
    release_status = _meta(text, "derived-release-status")
    if not release_status:
        errors.append("missing derived release status metadata")
    elif release_status == RELEASE_HOLD:
        errors.append("held report must not be released")

    fingerprint_values: dict[str, str] = {}
    for audit_key, meta_name in FINGERPRINT_META.items():
        value = _meta(text, meta_name)
        if not value or not re.fullmatch(r"[A-Fa-f0-9]{64}", value):
            errors.append(f"missing or invalid {meta_name} metadata")
        else:
            fingerprint_values[audit_key] = value

    if evidence_mode == "demo":
        badge_count = text.count(DEMO_BADGE)
        if badge_count != sheets:
            errors.append(f"demo badge count must equal page count: badges={badge_count}, pages={sheets}")
    elif evidence_mode == "actual":
        for phrase in ACTUAL_FORBIDDEN_DEMO_PHRASES:
            if phrase in text:
                errors.append(f"actual report contains demo wording: {phrase}")
                break
    else:
        errors.append("missing or invalid evidence-mode metadata")

    if report_type == "CHECKPOINT":
        expected_raw = _meta(text, "expected-pages")
        try:
            expected = int(expected_raw or "")
        except ValueError:
            expected = -1
            errors.append("missing or invalid expected-pages metadata")
        if expected >= 0 and sheets != expected:
            errors.append(f"checkpoint page count differs from plan: html={sheets}, expected={expected}")
        if len(re.findall(r'class=["\'][^"\']*\bclosing-paragraph\b', text, re.I)) != 5:
            errors.append("checkpoint closing must contain exactly five editorial paragraphs")
        chart_ids = ("chart-consulting", "chart-scatter", "chart-monthly", "chart-competition")
        for chart_id in chart_ids:
            if f'id="{chart_id}"' not in text and f"id='{chart_id}'" not in text:
                errors.append(f"missing checkpoint chart mount: {chart_id}")
        if "window.__REPORT_CHARTS_READY__ = true" not in text:
            errors.append("missing chart readiness signal")
        if customer_type == "SELL" and ("매수자에게" in text or "매수 행동" in text or "매수 판단" in text or re.search(r"\bBUY\b", text)):
            errors.append("SELL report contains BUY-facing question or action wording")
        if customer_type == "BUY" and ("매도자에게" in text or "매도 행동" in text or "매도 판단" in text or re.search(r"\bSELL\b", text)):
            errors.append("BUY report contains SELL-facing question or action wording")
    else:
        report_engine = _meta(text, "report-engine")
        report_engine_version = _meta(text, "report-engine-version")
        report_profile = _meta(text, "report-profile")
        if report_engine != "EZIWORK_GOLDEN_V3":
            errors.append("standard report must use EZIWORK_GOLDEN_V3")
        if report_engine_version != "3.1.0":
            errors.append("standard report must use engine version 3.1.0")
        if report_profile != "EXTENDED_9":
            errors.append("legacy compact profile is disabled")
        if "이번 분석을" not in text or "핵심 판단" not in text or "다음 행동" not in text:
            errors.append("closing page structure is incomplete")
        if "한눈에 설명" not in text:
            errors.append("missing customer takeaway label")
        if sheets != 9:
            errors.append(f"Golden V3 report must contain nine pages: html={sheets}")

    if request_data is not None:
        try:
            normalized, _warnings = migrate_request(request_data)
            audit = audit_request(normalized, base_dir)
            if audit["derived_release_status"] == RELEASE_HOLD:
                errors.append("request evidence audit is HOLD")
            for audit_key, meta_name in FINGERPRINT_META.items():
                if audit_key in fingerprint_values and fingerprint_values[audit_key].upper() != str(audit[audit_key]).upper():
                    errors.append(f"HTML {meta_name} differs from the request audit")
            if release_status and release_status != audit["derived_release_status"]:
                errors.append("HTML release status differs from the request audit")
            if normalized.get("report_type") == "checkpoint":
                route = str(normalized.get("customer_type", ""))
                view = selected_checkpoint_view(normalized, route)
                plan_errors = validate_page_plan(normalized, view)
                errors.extend(f"page plan: {error}" for error in plan_errors)
                expected = len(view.get("page_plan", {}).get("sequence", []))
                if sheets != expected:
                    errors.append(f"HTML page count differs from normalized request plan: {sheets} != {expected}")
            elif sheets != 9:
                errors.append(f"HTML page count differs from Golden V3 standard: {sheets} != 9")
        except Exception as exc:
            errors.append(f"cannot audit the request: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated customer-facing report HTML.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--request", type=Path, help="Original request JSON used to build the HTML")
    args = parser.parse_args()
    try:
        text = args.input.read_text(encoding="utf-8")
        request_data = json.loads(args.request.read_text(encoding="utf-8")) if args.request else None
        base_dir = args.request.resolve().parent if args.request else args.input.resolve().parent
        errors = validate_html(text, request_data, base_dir)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 3
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print(f"PASS: customer HTML checks ({_sheet_count(text)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
