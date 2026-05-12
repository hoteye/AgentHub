from __future__ import annotations

import json
from typing import Any

_DIAGNOSTIC_FIELD_DEFAULTS: dict[str, Any] = {
    "time_to_first_event_ms": None,
    "time_to_first_tool_ms": None,
    "initial_model_ms": None,
    "tool_execution_ms": None,
    "apply_patch_attempts": 0,
    "apply_patch_failures": 0,
    "fallback_edit_path_count": 0,
    "tool_call_sequence": [],
    "created_files": [],
    "validation_passed": False,
    "artifact_quality_notes": "",
}


def _prompt_preview(prompt: str, limit: int = 220) -> str:
    normalized = " ".join(str(prompt or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload
    for line in reversed(normalized.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_relative_ms(events: list[dict[str, Any]], *, tool_only: bool = False) -> int | None:
    for event in events:
        if tool_only and not _event_tool_name(event):
            continue
        for key in ("time_to_first_event_ms", "time_to_first_tool_ms", "t_rel_ms", "elapsed_ms", "relative_ms"):
            value = _int_or_none(event.get(key))
            if value is not None:
                return value
    return None


def _event_tool_name(event: dict[str, Any]) -> str:
    candidates = [
        event.get("name"),
        event.get("tool"),
        event.get("last_tool"),
        event.get("planner_execution_tool"),
        event.get("function_call_name"),
    ]
    payload = event.get("payload")
    if isinstance(payload, dict):
        candidates.extend(
            [
                payload.get("name"),
                payload.get("tool"),
                payload.get("planner_execution_tool"),
                payload.get("function_call_name"),
            ]
        )
    function = event.get("function")
    if isinstance(function, dict):
        candidates.append(function.get("name"))
    function_call = event.get("function_call")
    if isinstance(function_call, dict):
        candidates.append(function_call.get("name"))
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    event_type = str(event.get("type") or event.get("event") or "").strip()
    if "tool" in event_type:
        return event_type
    return ""


def _tool_name_matches(name: str, expected: str) -> bool:
    normalized = str(name or "").strip().lower()
    expected_normalized = str(expected or "").strip().lower()
    if not normalized or not expected_normalized:
        return False
    return (
        normalized == expected_normalized
        or normalized.endswith(f".{expected_normalized}")
        or normalized.endswith(f"/{expected_normalized}")
    )


def _event_text(event: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("summary", "output", "detail", "message", "error", "command", "command_text"):
        value = event.get(key)
        if value:
            parts.append(str(value))
    payload = event.get("payload")
    if isinstance(payload, dict):
        for key in ("summary", "output", "detail", "message", "error", "command", "command_text"):
            value = payload.get(key)
            if value:
                parts.append(str(value))
    return "\n".join(parts)


def _is_event_error(event: dict[str, Any]) -> bool:
    for key in ("ok", "success", "passed"):
        if key in event:
            return not bool(event.get(key))
    payload = event.get("payload")
    if isinstance(payload, dict):
        for key in ("ok", "success", "passed"):
            if key in payload:
                return not bool(payload.get(key))
    text = _event_text(event).lower()
    return any(fragment in text for fragment in ("failed", "error", "invalid", "traceback"))


def _tool_call_sequence(tool_events: list[dict[str, Any]], status: dict[str, Any] | None = None) -> list[str]:
    sequence: list[str] = []
    for event in tool_events:
        name = _event_tool_name(event)
        if name:
            sequence.append(name)
    if not sequence and isinstance(status, dict):
        last_tool = str(status.get("last_tool") or "").strip()
        if last_tool and last_tool != "-":
            sequence.append(last_tool)
    return sequence


def _count_tool_events(tool_events: list[dict[str, Any]], tool_name: str) -> tuple[int, int]:
    attempts = 0
    failures = 0
    for event in tool_events:
        if not _tool_name_matches(_event_tool_name(event), tool_name):
            continue
        attempts += 1
        if _is_event_error(event):
            failures += 1
    return attempts, failures


def _fallback_edit_path_count(tool_events: list[dict[str, Any]], *, apply_patch_failures: int) -> int:
    if apply_patch_failures <= 0:
        return 0
    count = 0
    for event in tool_events:
        if not _tool_name_matches(_event_tool_name(event), "exec_command"):
            continue
        text = _event_text(event).lower()
        if any(fragment in text for fragment in ("cat >", "tee ", "python - <<", "write_text", "touch ", "mkdir ")):
            count += 1
    return count or 1


def _artifact_quality_notes(
    *,
    run_succeeded: bool,
    validation_passed: bool,
    missing_expected_files: list[str],
    workspace_files: list[str],
) -> str:
    notes: list[str] = []
    notes.append("run_ok" if run_succeeded else "run_failed")
    notes.append("validation_ok" if validation_passed else "validation_failed")
    if missing_expected_files:
        notes.append("missing_expected=" + ",".join(missing_expected_files))
    else:
        notes.append("expected_files_present")
    notes.append(f"created_files={len(workspace_files)}")
    return "; ".join(notes)


def _diagnostic_defaults(**overrides: Any) -> dict[str, Any]:
    payload = {
        key: list(value) if isinstance(value, list) else value
        for key, value in _DIAGNOSTIC_FIELD_DEFAULTS.items()
    }
    payload.update(overrides)
    return payload


def _flatten_diagnostics(payload: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    stable = _diagnostic_defaults(**diagnostics)
    for key in _DIAGNOSTIC_FIELD_DEFAULTS:
        value = stable.get(key)
        payload[key] = list(value) if isinstance(value, list) else value
    payload["diagnostics"] = {
        key: list(value) if isinstance(value, list) else value
        for key, value in stable.items()
    }


def _agenthub_diagnostics(
    *,
    status: dict[str, Any],
    tool_events: list[dict[str, Any]],
    turn_events: list[dict[str, Any]],
) -> dict[str, Any]:
    first_event_ms = _first_relative_ms(turn_events)
    if first_event_ms is None:
        first_event_ms = _first_relative_ms(tool_events)
    apply_patch_attempts, apply_patch_failures = _count_tool_events(tool_events, "apply_patch")
    return _diagnostic_defaults(
        time_to_first_event_ms=first_event_ms,
        time_to_first_tool_ms=_first_relative_ms(tool_events, tool_only=True),
        initial_model_ms=_int_or_none(status.get("timing_initial_model_ms")),
        tool_execution_ms=_int_or_none(status.get("timing_tool_execution_ms")),
        apply_patch_attempts=apply_patch_attempts,
        apply_patch_failures=apply_patch_failures,
        fallback_edit_path_count=_fallback_edit_path_count(
            tool_events,
            apply_patch_failures=apply_patch_failures,
        ),
        tool_call_sequence=_tool_call_sequence(tool_events, status),
    )
