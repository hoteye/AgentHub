from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.command_execution_summary_runtime import (
    command_activity_params,
    command_display_text_from_mapping,
)
from cli.agent_cli.tools_core import tool_registry_runtime
from cli.agent_cli.models import (
    ActivityEvent,
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ToolEvent,
    compose_turn_events_from_response_items,
    default_response_items,
    prompt_response_turn_events,
)
from cli.agent_cli.models_response_items import response_items_phase_text
from cli.agent_cli.models_response_items import terminal_failure_message
from cli.agent_cli.models_turn_events_runtime import normalized_plan_payload
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.shell_command_handlers_runtime import parse_shell_action
from cli.agent_cli import runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service
from cli.agent_cli.runtime_core import (
    activity_detail_for_event as core_activity_detail_for_event,
    activity_events_for_tool_event as core_activity_events_for_tool_event,
    apply_tool_state as core_apply_tool_state,
    build_status_payload,
    detail_for_event as core_detail_for_event,
    snapshot_thread_state_payload,
)


def _command_activity_subject(source_text: str) -> str:
    compact = str(source_text or "").strip()
    if compact.lower().startswith("/shell "):
        try:
            action, shell_args = parse_shell_action(compact[len("/shell ") :].strip())
        except ValueError:
            return ""
        if action in {"write", "terminate", "stop"}:
            return ""
        return " ".join(shell_args).strip() if action == "start" else " ".join(shell_args).strip()
    if compact.lower().startswith("/exec_command"):
        positionals, options = parse_args(compact[len("/exec_command") :].strip())
        return str(options.get("cmd") or " ".join(positionals)).strip()
    return ""


def next_item_index(item_events: List[Dict[str, Any]]) -> int:
    highest = -1
    for event in list(item_events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("id") or "").strip()
        if not raw_id.startswith("item_"):
            continue
        try:
            highest = max(highest, int(raw_id.split("_", 1)[1]))
        except (TypeError, ValueError):
            continue
    return highest + 1


def turn_events_from_item_events(
    *,
    assistant_text: str,
    response_items: Optional[List[ResponseInputItem]] = None,
    item_events: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    normalized_response_items = list(
        response_items
        or default_response_items(
            assistant_text=str(assistant_text or ""),
        )
    )
    return compose_turn_events_from_response_items(
        assistant_text=str(assistant_text or ""),
        response_items=normalized_response_items,
        executed_item_events=[
            dict(item)
            for item in list(item_events or [])
            if isinstance(item, dict)
        ],
    )


def activity_events_for_tool_event(runtime: Any, event: ToolEvent) -> List[ActivityEvent]:
    return core_activity_events_for_tool_event(
        event,
        selected_conversation=runtime.selected_conversation,
    )


def activity_detail_for_event(event: ToolEvent) -> str:
    return core_activity_detail_for_event(event)


def detail_for_event(event: ToolEvent) -> str:
    return core_detail_for_event(event)


def apply_tool_state(runtime: Any, event: ToolEvent) -> None:
    (
        runtime.selected_conversation,
        runtime.pending_send_text,
        runtime.send_ready,
    ) = core_apply_tool_state(
        selected_conversation=runtime.selected_conversation,
        pending_send_text=runtime.pending_send_text,
        send_ready=runtime.send_ready,
        event=event,
    )


def build_activity_events(
    runtime: Any,
    *,
    source_text: str,
    tool_events: List[ToolEvent],
    handled_as_command: bool,
    plan: Optional[Dict[str, Any]] = None,
) -> List[ActivityEvent]:
    del handled_as_command
    activities: List[ActivityEvent] = []
    if plan:
        plan_activity = runtime._plan_activity_event(plan)
        if plan_activity is not None:
            activities.append(plan_activity)
    command = _command_activity_subject(source_text)
    if command:
        command_params = command_activity_params({"command": command})
        display_command = command_display_text_from_mapping(command_params, single_line=True) or command
        activities.append(
            ActivityEvent(
                title=f"Running {display_command}",
                status="running",
                kind="command",
                code="command.run",
                params=command_params,
            )
        )
    for event in tool_events:
        activities.extend(activity_events_for_tool_event(runtime, event))
    return activities


def build_status(
    runtime: Any,
    source_text: str,
    events: List[ToolEvent],
    *,
    timings: Optional[Dict[str, Any]] = None,
    protocol_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    provider_status = runtime.agent.provider_status()
    active_run_token = runtime.active_run_token()
    failure_message = terminal_failure_message(protocol_diagnostics=protocol_diagnostics)
    return build_status_payload(
        source_text=source_text,
        events=events,
        timings=timings,
        terminal_state="failed" if failure_message else "",
        error_message=failure_message,
        provider_status=provider_status,
        runtime_policy_status=runtime.runtime_policy_status(),
        approval_status=runtime.approval_status(),
        selected_conversation=runtime.selected_conversation,
        send_ready=runtime.send_ready,
        pending_send_text=runtime.pending_send_text,
        active_run_token=active_run_token,
        thread_id=runtime.thread_id,
        thread_name=runtime.thread_name,
    )


def build_response(
    runtime: Any,
    *,
    user_text: str,
    assistant_text: str,
    command_display_text: str = "",
    commentary_text: str = "",
    response_items: Optional[List[ResponseInputItem]] = None,
    attachments: List[PromptAttachment],
    reference_context_items: Optional[List[ReferenceContextItem]] = None,
    tool_events: List[ToolEvent],
    extra_activity_events: Optional[List[ActivityEvent]] = None,
    protocol_diagnostics: Optional[Dict[str, Any]] = None,
    source_text: str,
    handled_as_command: bool,
    plan: Optional[Dict[str, Any]] = None,
    timings: Optional[Dict[str, Any]] = None,
    turn_events: Optional[List[Dict[str, Any]]] = None,
) -> PromptResponse:
    normalized_commentary_text = str(commentary_text or "").strip()
    normalized_assistant_text = str(assistant_text or "")
    normalized_response_items = list(
        response_items
        or default_response_items(
            commentary_text=normalized_commentary_text,
            assistant_text=normalized_assistant_text,
        )
    )
    if not normalized_commentary_text:
        normalized_commentary_text = response_items_phase_text(
            normalized_response_items,
            phase="commentary",
        )
    merged_protocol_diagnostics = dict(protocol_diagnostics or {})
    headless_contract = dict(merged_protocol_diagnostics.get("headless_contract") or {})
    headless_contract["codex_noninteractive"] = bool(
        codex_headless_contract_runtime_service.runtime_uses_codex_noninteractive_contract(runtime)
    )
    merged_protocol_diagnostics["headless_contract"] = headless_contract
    response = PromptResponse(
        user_text=user_text,
        assistant_text=normalized_assistant_text,
        command_display_text=str(command_display_text or ""),
        commentary_text=normalized_commentary_text,
        response_items=normalized_response_items,
        attachments=list(attachments or []),
        reference_context_items=list(reference_context_items or []),
        tool_events=tool_events,
        activity_events=[
            *build_activity_events(
                runtime,
                source_text=source_text,
                tool_events=tool_events,
                handled_as_command=handled_as_command,
                plan=plan,
            ),
            *list(extra_activity_events or []),
        ],
        status=build_status(
            runtime,
            source_text,
            tool_events,
            timings=timings,
            protocol_diagnostics=merged_protocol_diagnostics,
        ),
        protocol_diagnostics=merged_protocol_diagnostics,
        timings=dict(timings or {}),
        handled_as_command=handled_as_command,
    )
    response.turn_events = [dict(item) for item in list(turn_events or []) if isinstance(item, dict)] or prompt_response_turn_events(response)
    return response


def snapshot_thread_state(runtime: Any) -> Dict[str, Any]:
    provider_status = runtime.agent.provider_status()
    payload = snapshot_thread_state_payload(
        provider_status=provider_status,
        runtime_policy_status=runtime.runtime_policy_status(),
        approval_status=runtime.approval_status(),
        selected_conversation=runtime.selected_conversation,
        pending_send_text=runtime.pending_send_text,
        send_ready=runtime.send_ready,
        thread_id=runtime.thread_id,
        thread_name=runtime.thread_name,
    )
    file_read_guard_state = tool_registry_runtime.normalized_file_read_guard_state_snapshot(
        getattr(runtime, "tools", None)
    )
    if file_read_guard_state:
        payload["file_read_guard_state"] = file_read_guard_state
    route_overrides_getter = getattr(runtime.agent, "session_route_overrides", None)
    if callable(route_overrides_getter):
        try:
            route_overrides = route_overrides_getter()
        except Exception:
            route_overrides = {}
        if isinstance(route_overrides, dict) and route_overrides:
            payload["session_route_overrides"] = {
                str(route_name): dict(item)
                for route_name, item in route_overrides.items()
                if isinstance(item, dict)
            }
    delegate_overrides_getter = getattr(runtime.agent, "session_delegate_overrides", None)
    if callable(delegate_overrides_getter):
        try:
            delegate_overrides = delegate_overrides_getter()
        except Exception:
            delegate_overrides = {}
        if isinstance(delegate_overrides, dict) and delegate_overrides:
            payload["session_delegation_overrides"] = {
                str(role_name): dict(item)
                for role_name, item in delegate_overrides.items()
                if isinstance(item, dict)
            }
    delegated_agents = runtime._delegated_agent_state_snapshot()
    if delegated_agents:
        payload["delegated_agents"] = delegated_agents
    latest_task_plan = normalized_plan_payload(getattr(runtime, "latest_task_plan", None))
    if latest_task_plan:
        payload["latest_task_plan"] = latest_task_plan
    payload["workspace_context_snapshot"] = dict(runtime._workspace_context_snapshot or {})
    payload["environment_context_snapshot"] = dict(runtime._environment_context_snapshot or {})
    payload["memory_context_snapshot"] = dict(getattr(runtime, "_memory_context_snapshot", {}) or {})
    payload["environment_context_history"] = [
        dict(item)
        for item in runtime._environment_context_history[-16:]
        if isinstance(item, dict)
    ]
    payload["context_update_history"] = [
        dict(item)
        for item in runtime._context_update_history[-16:]
        if isinstance(item, dict)
    ]
    return payload
