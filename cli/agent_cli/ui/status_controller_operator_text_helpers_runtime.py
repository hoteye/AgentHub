from __future__ import annotations

import json
import re
from typing import Any

from cli.agent_cli.ui import status_controller_operator_projection_helpers_runtime as _projection_helpers


OPERATOR_COMMANDS = frozenset(
    {
        "agent_workflow",
        "spawn_agent",
        "wait_agent",
        "send_input",
        "resume_agent",
        "close_agent",
        "background_task_status",
        "background_task_apply",
        "background_task_reject",
        "background_task_cancel",
        "background_task_retry",
    }
)
OPERATOR_AGGREGATE_COMMANDS = frozenset(
    {
        "workflows",
        "background_tasks",
        "background_worker_status",
        "background_worker_start",
        "background_worker_stop",
        "background_worker_run_once",
    }
)
OPERATOR_TEXT_COMMANDS = OPERATOR_COMMANDS | OPERATOR_AGGREGATE_COMMANDS

OPERATOR_STATUS_KEYS = _projection_helpers.OPERATOR_STATUS_KEYS
status_text = _projection_helpers.status_text
_ELLIPSIS = "\u2026"


def operator_command_name(user_text: Any) -> str:
    text = str(user_text or "").strip()
    if not text.startswith("/"):
        return ""
    match = re.match(r"^/([A-Za-z0-9_-]+)\b", text)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


def key_value_lines(text: Any) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        extracted[normalized_key] = status_text(value)
    return extracted


def operator_status_from_text(key_values: dict[str, str]) -> dict[str, str]:
    return {
        normalized_key: status_text(value)
        for normalized_key, value in dict(key_values or {}).items()
        if normalized_key in OPERATOR_STATUS_KEYS
    }


def policy_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    text = str(value or "").strip()
    if not text or text == "-":
        return []
    try:
        loaded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        return [loaded]
    return []


def policy_surface_hint(value: Any) -> str:
    entries = policy_entries(value)
    if not entries:
        return ""
    denied = [item for item in entries if bool(item.get("policy_denied"))]
    if denied:
        denied_cmd = str(
            denied[0].get("command") or denied[0].get("effective_command") or ""
        ).strip()
        return f"policy denied {tool_label(denied_cmd, 28)}" if denied_cmd else "policy denied"
    rewritten = []
    for item in entries:
        command = str(item.get("command") or "").strip()
        effective = str(item.get("effective_command") or "").strip()
        if command and effective and command != effective:
            rewritten.append((command, effective))
    if rewritten:
        source, target = rewritten[0]
        return f"policy rewrite {tool_label(source, 18)} -> {tool_label(target, 24)}"
    return f"policy checked {len(entries)}"


def tool_label(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: max(1, limit - 1)] + _ELLIPSIS
