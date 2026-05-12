from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    shell_command_assistant_text,
    shell_tool_call_item_events,
)
from cli.agent_cli.runtime_services import command_policy_runtime
from cli.agent_cli.runtime_services import shell_runtime_payload_runtime


def shell_command_text(command: str, *, exec_mode: str) -> str:
    normalized_command = str(command or "").strip()
    if exec_mode == "session_start":
        return f"/shell start {normalized_command}"
    return f"/shell {normalized_command}"


def shell_start_event_from_session(
    session: Dict[str, Any],
    *,
    command: str,
    exec_mode: str,
) -> ToolEvent:
    payload, session_id, process_id = shell_runtime_payload_runtime.shell_start_payload(
        session,
        command=command,
        exec_mode=exec_mode,
    )
    if session_id:
        return ToolEvent(
            name="shell_start",
            ok=True,
            summary=f"shell session started {session_id}",
            payload=payload,
        )
    return ToolEvent(
        name="shell_start",
        ok=False,
        summary="shell session start failed",
        payload={**payload, "error": "shell_start did not return session_id", "status": "start_failed"},
    )


def shell_result_from_event(
    assistant_text: str,
    event: ToolEvent,
    *,
    command: str | None = None,
) -> CommandExecutionResult:
    normalized_command = str(command or shell_runtime_payload_runtime.event_command(event) or "").strip() or None
    return CommandExecutionResult(
        assistant_text=shell_command_assistant_text(str(assistant_text or ""), event),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=normalized_command),
    )


def _command_policy_decision(command: str) -> command_policy_runtime.CommandPolicyDecision:
    return command_policy_runtime.evaluate_command_policy(command)


def _policy_denied_result(
    assistant_text: str,
    decision: command_policy_runtime.CommandPolicyDecision,
    *,
    tool_name: str,
) -> CommandExecutionResult:
    event = command_policy_runtime.policy_denied_tool_event(
        tool_name=tool_name,
        decision=decision,
    )
    normalized_command = str(decision.command or "").strip() or None
    return CommandExecutionResult(
        assistant_text=str(assistant_text or decision.error_message or "command denied by policy"),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=normalized_command),
    )
