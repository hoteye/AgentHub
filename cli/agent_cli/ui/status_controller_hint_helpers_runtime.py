from __future__ import annotations

import json
from typing import Any, Callable


def operator_hint_title(assistant_text: Any) -> str:
    for raw_line in str(assistant_text or "").splitlines():
        line = str(raw_line or "").strip()
        if line:
            return line
    return ""


def json_compact(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def count_compact(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    text = str(value or "").strip()
    if text.isdigit():
        return max(0, int(text))
    parsed = json_compact(value)
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        return len(parsed)
    return 0


def string_items_compact(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip() and str(item).strip() != "-"]
    parsed = json_compact(value)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip() and str(item).strip() != "-"]
    text = str(value or "").strip()
    if not text or text == "-":
        return []
    if "," in text:
        return [segment.strip() for segment in text.split(",") if segment.strip() and segment.strip() != "-"]
    return [text]


def card_ids_compact(value: Any) -> list[str]:
    parsed = json_compact(value)
    if not isinstance(parsed, list):
        return []
    card_ids: list[str] = []
    for item in parsed:
        if isinstance(item, dict):
            card_id = str(item.get("card_id") or "").strip()
            if card_id:
                card_ids.append(card_id)
    return card_ids


def preview_items(items: list[str], *, limit: int = 3) -> str:
    compact = [str(item).strip() for item in list(items or []) if str(item).strip()]
    if not compact:
        return ""
    head = compact[: max(1, int(limit))]
    if len(compact) <= len(head):
        return ",".join(head)
    return f"{','.join(head)} +{len(compact) - len(head)}"


def operator_next_command(value: Any) -> str:
    parsed = json_compact(value)
    if not isinstance(parsed, list):
        return ""
    for item in parsed:
        if not isinstance(item, dict):
            continue
        command_name = str(item.get("command_name") or "").strip()
        if command_name:
            return command_name
        command = str(item.get("command") or "").strip()
        if command:
            return command.split(" ", 1)[0].strip()
    return ""


def tenant_scope_parts(
    tenant_id: str,
    workspace_scope: str,
    tenant_scope_profile: str = "",
    *,
    tool_label_fn: Callable[[str], str],
) -> list[str]:
    parts: list[str] = []
    tenant_text = str(tenant_id or "").strip()
    workspace_text = str(workspace_scope or "").strip()
    profile_text = str(tenant_scope_profile or "").strip().lower()
    if profile_text not in {"default", "isolated"}:
        if tenant_text or workspace_text:
            profile_text = (
                "default"
                if tenant_text.lower() == "default" and workspace_text.lower() == "default"
                else "isolated"
            )
    if profile_text in {"default", "isolated"}:
        parts.append(f"scope {tool_label_fn(profile_text)}")
    if tenant_text not in {"", "-"}:
        parts.append(f"tenant {tool_label_fn(tenant_text)}")
    if workspace_text not in {"", "-"}:
        parts.append(f"scope {tool_label_fn(workspace_text)}")
    return parts


def count_from_key_values(
    key_values: dict[str, str],
    key: str,
    *,
    normalized_count_fn: Callable[[Any], str],
) -> int:
    count_text = normalized_count_fn(key_values.get(key))
    try:
        return max(0, int(count_text))
    except (TypeError, ValueError):
        return 0
