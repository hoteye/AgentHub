from __future__ import annotations

from typing import Any, Iterable

from cli.agent_cli.models import (
    tool_event_is_soft_failure,
    tool_events_include_interrupt,
)


def build_app_server_gateway_extension_methods(
    *,
    base_methods: tuple[str, ...],
    gateway_methods: Iterable[str],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set(base_methods)
    for method in gateway_methods:
        key = str(method or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def completed_turn_status(response: Any) -> str:
    status = dict(getattr(response, "status", {}) or {})
    terminal_state = str(status.get("terminal_state") or "").strip().lower()
    if terminal_state in {"completed", "interrupted", "failed"}:
        return terminal_state
    tool_events = list(getattr(response, "tool_events", []) or [])
    if tool_events_include_interrupt(tool_events):
        return "interrupted"
    if any((not bool(getattr(item, "ok", False))) and not tool_event_is_soft_failure(item) for item in tool_events):
        return "failed"
    return "completed"


def turn_error_message(response: Any) -> str:
    status = dict(getattr(response, "status", {}) or {})
    message = str(status.get("error") or "").strip()
    if message:
        return message
    diagnostics = dict(getattr(response, "protocol_diagnostics", {}) or {})
    terminal_state = dict(diagnostics.get("turn_terminal_state") or {})
    for key in ("error_message", "message", "detail"):
        text = str(terminal_state.get(key) or "").strip()
        if text:
            return text
    for tool_event in reversed(list(getattr(response, "tool_events", []) or [])):
        if bool(getattr(tool_event, "ok", False)):
            continue
        payload = dict(getattr(tool_event, "payload", {}) or {})
        for key in ("error", "stderr", "message"):
            text = str(payload.get(key) or "").strip()
            if text:
                return text
        summary = str(getattr(tool_event, "summary", "") or getattr(tool_event, "name", "") or "").strip()
        if summary:
            return summary
    return ""


def text_delta(previous: str, current: str) -> str:
    previous_text = str(previous or "")
    current_text = str(current or "")
    if not current_text:
        return ""
    if current_text.startswith(previous_text):
        return current_text[len(previous_text) :]
    return current_text


def raw_response_item_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        payload = dict(item)
    else:
        to_dict = getattr(item, "to_dict", None)
        if not callable(to_dict):
            return None
        payload = to_dict()
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def turn_stream_item_text(event: dict[str, Any], item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip()
    if item_type == "commandExecution":
        return str(item.get("aggregatedOutput") or dict(event.get("updated") or {}).get("text") or "")
    if item_type == "agentMessage":
        return str(item.get("text") or "")
    if item_type == "plan":
        return str(item.get("text") or "")
    if item_type == "reasoning":
        content = item.get("content")
        if isinstance(content, list):
            parts = [str(entry or "").strip() for entry in content if str(entry or "").strip()]
            if parts:
                return "\n\n".join(parts)
        return str(dict(event.get("item") or {}).get("text") or "")
    return ""
