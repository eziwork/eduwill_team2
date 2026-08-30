from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated customer-facing report HTML.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--request", type=Path, help="Original request JSON used to build the HTML")
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8")
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
    if "이번 분석을" not in text or "핵심 판단" not in text or "다음 행동" not in text:
        errors.append("closing page structure is incomplete")
    if "한눈에 설명" not in text:
        errors.append("missing customer takeaway label")
    if "EZIWORK" not in text and "cover-brand" not in text:
        errors.append("brand mark is missing")
    if "<html" not in text.lower() or "@page" not in text:
        errors.append("standalone print-ready HTML structure is missing")
    fingerprint_match = re.search(r'<meta\s+name="evidence-audit-sha256"\s+content="([A-Fa-f0-9]{64})"', text)
    release_match = re.search(r'<meta\s+name="derived-release-status"\s+content="([^"]+)"', text)
    if not fingerprint_match:
        errors.append("missing evidence audit fingerprint metadata")
    if not release_match:
        errors.append("missing derived release status metadata")
    elif release_match.group(1) == RELEASE_HOLD:
        errors.append("held report must not be released")
    if args.request:
        try:
            request_data = json.loads(args.request.read_text(encoding="utf-8"))
            audit = audit_request(request_data, args.request.resolve().parent)
            if audit["derived_release_status"] == RELEASE_HOLD:
                errors.append("request evidence audit is HOLD")
            if fingerprint_match and fingerprint_match.group(1).upper() != audit["evidence_fingerprint"].upper():
                errors.append("HTML evidence fingerprint differs from the request audit")
            if release_match and release_match.group(1) != audit["derived_release_status"]:
                errors.append("HTML release status differs from the request audit")
        except Exception as exc:
            errors.append(f"cannot audit the request: {exc}")
    sheets = len(re.findall(r'class="sheet(?:\s|\")', text))
    if sheets < 5:
        errors.append(f"unexpectedly short report: {sheets} pages")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print(f"PASS: customer HTML checks ({sheets} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
