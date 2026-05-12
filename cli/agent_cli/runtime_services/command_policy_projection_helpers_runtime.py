from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ToolEvent


def command_policy_payload(
    decision: Any,
    *,
    policy_denied_status: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": decision.command,
        "effective_command": decision.effective_command,
        "allowed": decision.allowed,
        "status": "allowed" if decision.allowed else policy_denied_status,
        "policy_mode": decision.policy_mode,
        "test_policy": decision.test_policy,
        "is_test_command": decision.is_test_command,
        "test_command_kind": decision.test_command_kind,
    }
    if decision.error_code:
        payload["error_code"] = decision.error_code
    if decision.error_message:
        payload["error"] = decision.error_message
        payload["output_text"] = decision.error_message
        payload["text"] = decision.error_message
    if decision.metadata:
        payload.update(dict(decision.metadata))
    return payload


def wrap_tool_event_with_policy(
    event: ToolEvent,
    *,
    decision: Any,
) -> ToolEvent:
    payload = dict(event.payload or {})
    payload["command"] = decision.command
    if decision.effective_command and decision.effective_command != decision.command:
        payload["effective_command"] = decision.effective_command
    if decision.is_test_command or decision.metadata:
        payload["command_policy"] = decision.payload()
    return ToolEvent(
        name=event.name,
        ok=event.ok,
        summary=event.summary,
        payload=payload,
    )


def policy_denied_tool_event(
    *,
    tool_name: str,
    decision: Any,
    policy_denied_status: str,
) -> ToolEvent:
    payload = decision.payload()
    payload.setdefault("command", decision.command)
    payload["status"] = policy_denied_status
    return ToolEvent(
        name=tool_name,
        ok=False,
        summary="command policy denied",
        payload=payload,
    )
