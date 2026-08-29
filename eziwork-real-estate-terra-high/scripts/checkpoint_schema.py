from __future__ import annotations

import copy
from typing import Any


REPORT_CHECKPOINT = "checkpoint"


def migrate_request(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize the standard request without exposing the removed nine-page route."""
    normalized = copy.deepcopy(data)
    warnings: list[str] = []
    normalized.setdefault("report_type", "standard")
    if normalized.get("report_type") == REPORT_CHECKPOINT:
        return normalized, ["checkpoint reports are not supported by the EZIWORK educational release"]
    if str(normalized.get("schema_version", "")) in {"1", "1.0"}:
        normalized["schema_version"] = "2.0"
        warnings.append("v1 request was migrated in memory to schema_version 2.0")
    return normalized, warnings


def selected_checkpoint_view(data: dict[str, Any], route: str | None = None) -> dict[str, Any]:
    raise ValueError("the nine-page checkpoint route is not included in this educational release")


def validate_page_plan(data: dict[str, Any], view: dict[str, Any]) -> list[str]:
    return ["the nine-page checkpoint route is not included in this educational release"]
