from __future__ import annotations

from typing import Any


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def tool_event_payload(tool_event: Any) -> dict[str, Any]:
    return dict(getattr(tool_event, "payload", {}) or {})


def shell_action_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    argv_value = payload.get("argv")
    if isinstance(argv_value, (list, tuple)):
        command_parts = [str(item).strip() for item in argv_value if str(item).strip()]
    else:
        raw_command = str(payload.get("command") or "").strip()
        command_parts = [raw_command] if raw_command else []
    action: dict[str, Any] = {
        "type": "exec",
        "command": command_parts,
    }
    timeout_ms = payload.get("timeout_ms")
    if timeout_ms is not None:
        action["timeout_ms"] = timeout_ms
    workdir = str(payload.get("workdir") or payload.get("working_directory") or "").strip()
    if workdir:
        action["working_directory"] = workdir
    max_output_length = payload.get("max_output_length", payload.get("max_output_chars"))
    if max_output_length is not None:
        action["max_output_length"] = max_output_length
    return action


def compact_argument_map(arguments: dict[str, Any] | None) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def first_change_path(payload: dict[str, Any]) -> str:
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        return ""
    first = changes[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("path") or "").strip()


__all__ = [
    "compact_argument_map",
    "first_change_path",
    "safe_int",
    "shell_action_from_payload",
    "tool_event_payload",
]
