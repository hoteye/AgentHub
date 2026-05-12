from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli.tools_core.browser_action_normalization import browser_event_name


def _browser_summary(action: str, payload: Dict[str, Any], *, event_name: str) -> str:
    if payload is None:
        return f"{event_name.replace('_', ' ')}"
    summary = str(payload.get("summary") or payload.get("action") or payload.get("status") or "").strip()
    if summary:
        return summary
    return f"{event_name.replace('_', ' ')}"


def browser_action_result(
    *,
    action: str,
    payload: Dict[str, Any] | None = None,
    arguments: Dict[str, Any] | None = None,
    tool_name: str = "browser",
) -> CommandExecutionResult:
    event_name = browser_event_name(action)
    normalized_payload = dict(payload or {})
    ok = bool(normalized_payload.get("ok", True))
    summary = _browser_summary(action, normalized_payload, event_name=event_name)
    event = ToolEvent(
        name=event_name,
        ok=ok,
        summary=summary,
        payload=normalized_payload,
    )
    return CommandExecutionResult(
        assistant_text=summary,
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=str(tool_name or "browser").strip(),
            arguments={
                "action": action,
                **dict(arguments or {}),
            }
            if arguments is not None
            else {"action": action},
            ok=bool(event.ok),
            summary=summary,
            structured_content=normalized_payload,
        ),
    )
