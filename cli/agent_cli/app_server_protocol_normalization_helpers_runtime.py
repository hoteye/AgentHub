from __future__ import annotations

from typing import Any


def booleanish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def parse_cursor(raw_cursor: Any) -> int:
    if raw_cursor in (None, "", False):
        return 0
    try:
        cursor = int(str(raw_cursor))
    except (TypeError, ValueError):
        raise ValueError(f"invalid cursor: {raw_cursor}") from None
    if cursor < 0:
        raise ValueError(f"invalid cursor: {raw_cursor}")
    return cursor


def paginate_items(items: list[Any], *, cursor: int, limit: int | None) -> tuple[list[Any], str | None]:
    start = min(cursor, len(items))
    if limit == 0:
        return [], None
    end = len(items) if limit is None else min(len(items), start + limit)
    next_cursor = str(end) if end < len(items) else None
    return items[start:end], next_cursor


def parse_limit(params: dict[str, Any]) -> int | None:
    limit = params.get("limit")
    if limit is None:
        return None
    try:
        resolved = int(limit)
    except (TypeError, ValueError):
        raise ValueError(f"invalid limit: {limit}") from None
    if resolved < 0:
        raise ValueError(f"invalid limit: {limit}")
    return resolved


def reference_approval_policy_value(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {
        "never": "never",
        "on-request": "on-request",
        "on-failure": "on-failure",
        "untrusted": "untrusted",
        "unless-trusted": "untrusted",
    }
    return mapping.get(normalized, "never")


def reasoning_effort_value(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return normalized
    return None


def service_tier_value(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"fast", "flex"}:
        return normalized
    return None


def model_hidden(item: dict[str, Any]) -> bool:
    if "hidden" in item:
        return booleanish(item.get("hidden"))
    if "show_in_picker" in item:
        return not booleanish(item.get("show_in_picker"), default=True)
    return False


def reference_turn_plan_step_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"completed", "done"}:
        return "completed"
    if normalized in {"in_progress", "in-progress", "inprogress", "running", "active"}:
        return "inProgress"
    return "pending"
