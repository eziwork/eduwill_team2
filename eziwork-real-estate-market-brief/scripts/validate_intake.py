from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TASK_MODES = {"MARKET_REPORT", "MARKET_REPORT_WITH_MATCHING"}
EVIDENCE_MODES = {"actual", "demo"}
PROPERTY_TYPES = {"APT", "ROWHOUSE", "DETACHED_HOUSE", "OFFICETEL", "LAND", "COMMERCIAL"}
TRADE_TYPES = {"SALE", "JEONSE", "MONTHLY_RENT"}
ROLES = {"BUY", "SELL", "TENANT", "LANDLORD", "OWNER", "OPERATOR"}
BUILDING_MODES = {"ALL", "SELECTED", "NOT_APPLICABLE"}
AREA_MODES = {"ALL", "SELECTED", "NOT_APPLICABLE"}
HISTORY_YEARS = {1, 3, 5, 7}
COMMUNICATION_MODES = {"CUSTOMER_SALES", "BUYER_ADVISORY"}
REPORT_PROFILES = {"AUTO", "COMPACT_6", "EXTENDED_9"}
CONVERSION_GOALS = {"SITE_VISIT_CONSULTATION", "INFORMED_DECISION"}
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_LOGO_BYTES = 5 * 1024 * 1024
OFFICIAL_ROUTES = {
    (property_type, trade_type)
    for property_type in {"APT", "ROWHOUSE", "DETACHED_HOUSE", "OFFICETEL"}
    for trade_type in TRADE_TYPES
} | {("LAND", "SALE"), ("COMMERCIAL", "SALE")}


def load_intake(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("intake must be a JSON object")
    return data


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_intake(data: dict[str, Any], base_dir: Path | None = None) -> tuple[list[str], list[str]]:
    base_dir = (base_dir or Path.cwd()).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("intake_version") != "1.0":
        errors.append("intake_version must be 1.0")
    if data.get("task_mode") not in TASK_MODES:
        errors.append("task_mode must be MARKET_REPORT or MARKET_REPORT_WITH_MATCHING")
    if data.get("evidence_mode") not in EVIDENCE_MODES:
        errors.append("evidence_mode must be actual or demo")
    if not _nonempty_string(data.get("report_id")):
        errors.append("report_id is required")
    if not _nonempty_string(data.get("basis_date")):
        errors.append("basis_date is required")

    target = data.get("target") if isinstance(data.get("target"), dict) else {}
    property_type = str(target.get("property_type", ""))
    if not _nonempty_string(target.get("name")):
        errors.append("target.name is required")
    if not (_nonempty_string(target.get("address")) or _nonempty_string(target.get("lot_number_hint"))):
        errors.append("target.address or target.lot_number_hint is required")
    if property_type not in PROPERTY_TYPES:
        errors.append("target.property_type is unsupported")

    transaction = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
    trade_type = str(transaction.get("trade_type", ""))
    if trade_type not in TRADE_TYPES:
        errors.append("transaction.trade_type is unsupported")

    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    if customer.get("role") not in ROLES:
        errors.append("customer.role is unsupported")
    if not _nonempty_string(customer.get("decision_question")):
        errors.append("customer.decision_question is required")

    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    brand_name = output.get("brand_name")
    logo_path = output.get("logo_path")
    if data.get("evidence_mode") == "actual" and not _nonempty_string(brand_name):
        errors.append("output.brand_name is required for an actual customer report")
    if data.get("evidence_mode") == "actual" and not _nonempty_string(logo_path):
        errors.append("output.logo_path is required for an actual customer report")
    if _nonempty_string(logo_path):
        resolved_logo = Path(str(logo_path))
        resolved_logo = resolved_logo if resolved_logo.is_absolute() else base_dir / resolved_logo
        resolved_logo = resolved_logo.resolve()
        if resolved_logo.suffix.lower() not in LOGO_SUFFIXES:
            errors.append("output.logo_path must be PNG, JPG, JPEG, WEBP, or SVG")
        elif not resolved_logo.is_file():
            errors.append(f"output.logo_path file not found: {resolved_logo}")
        elif resolved_logo.stat().st_size > MAX_LOGO_BYTES:
            errors.append("output.logo_path must be 5 MB or smaller")

    communication = data.get("communication") if isinstance(data.get("communication"), dict) else {}
    if communication:
        if communication.get("mode", "CUSTOMER_SALES") not in COMMUNICATION_MODES:
            errors.append("communication.mode is unsupported")
        if communication.get("report_profile", "AUTO") not in REPORT_PROFILES:
            errors.append("communication.report_profile is unsupported")
        if communication.get("conversion_goal", "SITE_VISIT_CONSULTATION") not in CONVERSION_GOALS:
            errors.append("communication.conversion_goal is unsupported")

    period = data.get("period") if isinstance(data.get("period"), dict) else {}
    if period.get("history_years") not in HISTORY_YEARS:
        errors.append("period.history_years must be one of 1, 3, 5, or 7")

    decision_context = data.get("decision_context") if isinstance(data.get("decision_context"), dict) else {}
    for field in ("budget_krw", "intended_holding_years"):
        value = decision_context.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            errors.append(f"decision_context.{field} must be a positive number when provided")

    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    building_mode = scope.get("building_mode", "NOT_APPLICABLE")
    area_mode = scope.get("area_mode", "NOT_APPLICABLE")
    if building_mode not in BUILDING_MODES:
        errors.append("scope.building_mode is invalid")
    if area_mode not in AREA_MODES:
        errors.append("scope.area_mode is invalid")
    if building_mode == "SELECTED" and not scope.get("building_names"):
        errors.append("scope.building_names is required for SELECTED building_mode")
    area_min = scope.get("requested_area_min_sqm")
    area_max = scope.get("requested_area_max_sqm")
    if area_mode == "SELECTED" and area_min is None and area_max is None:
        errors.append("an area minimum or maximum is required for SELECTED area_mode")
    if area_min is not None and area_max is not None:
        try:
            if float(area_min) > float(area_max):
                errors.append("scope area minimum cannot exceed maximum")
        except (TypeError, ValueError):
            errors.append("scope area values must be numeric")

    collection = data.get("collection") if isinstance(data.get("collection"), dict) else {}
    if collection.get("permission_mode", "RESEARCH_SAMPLE") != "RESEARCH_SAMPLE":
        errors.append("this educational release supports only RESEARCH_SAMPLE")
    max_pages = collection.get("max_detail_pages", 10)
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 0 <= max_pages <= 10:
        errors.append("collection.max_detail_pages must be an integer from 0 to 10")

    route_supported = (property_type, trade_type) in OFFICIAL_ROUTES
    if data.get("evidence_mode") == "actual" and route_supported:
        lawd_cd = str(target.get("lawd_cd", ""))
        if len(lawd_cd) != 5 or not lawd_cd.isdigit():
            errors.append("target.lawd_cd must contain five digits for actual official collection")
    if not route_supported and property_type in PROPERTY_TYPES and trade_type in TRADE_TYPES:
        warnings.append(f"no bundled official unit route for {property_type}/{trade_type}; use traceable supplied evidence or mark unavailable")

    if property_type in {"APT", "ROWHOUSE", "OFFICETEL"} and area_mode == "NOT_APPLICABLE":
        warnings.append("an exclusive-area scope is normally needed for comparable selection")
    if property_type in {"DETACHED_HOUSE", "LAND", "COMMERCIAL"} and area_mode == "ALL":
        warnings.append("district-wide area scope may be too broad; record the explicit comparable rule")

    if data.get("task_mode") == "MARKET_REPORT_WITH_MATCHING":
        matching = data.get("matching") if isinstance(data.get("matching"), dict) else {}
        candidate_path = matching.get("candidates_path")
        if not _nonempty_string(candidate_path):
            errors.append("matching.candidates_path is required for MARKET_REPORT_WITH_MATCHING")
        else:
            resolved = Path(candidate_path)
            resolved = resolved if resolved.is_absolute() else base_dir / resolved
            if not resolved.is_file():
                errors.append(f"matching candidate file not found: {resolved.resolve()}")
        if not matching.get("must_haves") and not matching.get("preferences"):
            errors.append("matching needs at least one must-have or preference")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate EZIWORK real-estate intake v1.0.")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        data = load_intake(args.input)
        errors, warnings = validate_intake(data, args.input.resolve().parent)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print("VALID: intake v1.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
