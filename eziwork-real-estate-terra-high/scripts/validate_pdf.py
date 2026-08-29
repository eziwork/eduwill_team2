from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from checkpoint_schema import migrate_request, selected_checkpoint_view
from evidence_audit import RELEASE_HOLD, audit_request


DEMO_BADGE = "교육용 예시 · 실제 시세가 아님"
CHART_PAGE_IDS = {
    "price-position",
    "transaction-distribution",
    "market-activity",
    "current-competition",
}
A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89


def _page_text(page: Any) -> str:
    return page.extract_text() or ""


def validate_pdf(pdf_path: Path, request_data: dict[str, Any], base_dir: Path, html_text: str | None = None) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency error is reported by the CLI
        raise RuntimeError("pypdf is required to validate PDF output") from exc

    normalized, _warnings = migrate_request(request_data)
    audit = audit_request(normalized, base_dir)
    errors: list[str] = []
    if audit["derived_release_status"] == RELEASE_HOLD:
        errors.append("request evidence audit is HOLD")
    reader = PdfReader(str(pdf_path))
    is_checkpoint = normalized.get("report_type") == "checkpoint"
    view = selected_checkpoint_view(normalized, str(normalized.get("customer_type", ""))) if is_checkpoint else {}
    sequence = view.get("page_plan", {}).get("sequence", [])
    expected_pages = len(sequence) if is_checkpoint else int(normalized.get("report_engine", {}).get("page_count", 9))
    if expected_pages is not None and len(reader.pages) != expected_pages:
        errors.append(f"PDF page count differs from page plan: pdf={len(reader.pages)}, expected={expected_pages}")

    all_text: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if abs(width - A4_WIDTH_PT) > 3 or abs(height - A4_HEIGHT_PT) > 3:
            errors.append(f"page {index} is not A4: {width:.1f} x {height:.1f} pt")
        text = _page_text(page)
        all_text.append(text)
        if len(re.sub(r"\s+", "", text)) < 10:
            errors.append(f"page {index} appears blank")

    combined_text = "\n".join(all_text)
    target_name = str(normalized.get("target", {}).get("name", ""))
    if target_name and target_name not in combined_text:
        errors.append("PDF is missing the target property name")
    evidence_mode = str(normalized.get("evidence_mode", ""))
    if evidence_mode == "demo":
        for index, text in enumerate(all_text, start=1):
            if DEMO_BADGE not in text:
                errors.append(f"page {index} is missing the demo badge")
    elif evidence_mode == "actual" and ("교육용 예시" in combined_text or "실제 시세가 아님" in combined_text):
        errors.append("actual PDF contains demo wording")

    verification_id = str(audit["combined_release_fingerprint"])[:16]
    compact_text = re.sub(r"\s+", "", combined_text)
    if verification_id not in compact_text:
        errors.append("PDF does not contain the audited combined release fingerprint")
    if html_text is not None:
        match = re.search(r'<meta\s+name=["\']combined-release-sha256["\']\s+content=["\']([A-Fa-f0-9]{64})', html_text, re.I)
        if not match or match.group(1).lower() != str(audit["combined_release_fingerprint"]).lower():
            errors.append("HTML and PDF request do not share the same release fingerprint")

    if is_checkpoint:
        prologue_map = {str(page.get("page_id", "")): page for page in view.get("prologue_pages", [])}
        analysis_map = {str(page.get("page_id", "")): page for page in view.get("analysis_pages", [])}
        title_map = {
            "cover": view.get("cover", {}),
            "property": view.get("property_page", {}),
            **prologue_map,
            **analysis_map,
        }
        for page_id, page in title_map.items():
            if page_id not in sequence:
                continue
            lines = page.get("title_lines", []) if isinstance(page, dict) else []
            if isinstance(lines, str):
                lines = [lines]
            expected_title = next((re.sub(r"\*\*|\s+", "", str(line)) for line in lines if str(line).strip()), "")
            if expected_title:
                page_text = re.sub(r"\s+", "", all_text[sequence.index(page_id)])
                if expected_title not in page_text:
                    errors.append(f"page {sequence.index(page_id) + 1} is missing its major title: {page_id}")
        for page_id in CHART_PAGE_IDS:
            if page_id not in sequence:
                continue
            page_index = sequence.index(page_id)
            if page_index >= len(reader.pages):
                continue
            contents = reader.pages[page_index].get_contents()
            raw = contents.get_data() if contents is not None else b""
            draw_ops = len(re.findall(rb"(?:^|\s)(?:m|l|c|re|S|s|f|f\*)(?:\s|$)", raw))
            if len(raw) < 2500 or draw_ops < 12:
                errors.append(f"chart graphics appear missing on {page_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a rendered customer report PDF.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()
    try:
        request_data = json.loads(args.request.read_text(encoding="utf-8"))
        html_text = args.html.read_text(encoding="utf-8") if args.html else None
        errors = validate_pdf(args.input, request_data, args.request.resolve().parent, html_text)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 3
    except Exception as exc:
        print(f"ERROR: PDF validation runtime failure: {exc}")
        return 3
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print(f"PASS: PDF checks ({args.input})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
