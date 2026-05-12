from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.app_server_shell_protocol import (
    _compose_command_turn_events,
    _shell_activity_to_event,
    _shell_activity_to_turn_event,
)
from cli.agent_cli.command_execution_summary_runtime import command_activity_params
from cli.agent_cli.gateway_api import gui_bridge_payloads as gui_bridge_payloads_service
from cli.agent_cli.gateway_api.gui_bridge_action_threads_runtime import (
    _history_turn_payload,
    _runtime_state_snapshot,
)
from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent

GuiBridgeResponseBuilder = Callable[..., dict[str, Any]]


def shell_run(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    command = _shell_run_command(payload)
    if not command:
        return error(
            request_id=request_id,
            action=action,
            code="shell.run.invalid_payload",
            message="command is required",
        )
    activity_events: list[ActivityEvent] = []
    item_events: list[dict[str, Any]] = []

    def on_activity(activity_payload: dict[str, Any]) -> None:
        activity_event = _shell_activity_to_event(activity_payload)
        if activity_event is not None:
            activity_events.append(activity_event)
        turn_event = _shell_activity_to_turn_event(activity_payload)
        if turn_event is not None:
            item_events.append(dict(turn_event))

    result = runtime.begin_shell_request(
        command,
        requested_by="gui",
        exec_mode="exec_once",
        cwd=_shell_run_cwd(payload),
        timeout_sec=_shell_run_timeout_sec(payload),
        login=_payload_bool(payload, "login", default=True),
        tty=_payload_bool(payload, "tty", default=False),
        shell=_payload_optional_text(payload, "shell"),
        max_output_chars=_payload_int(
            payload,
            "max_output_chars",
            default=12000,
            minimum=1000,
            maximum=60000,
        ),
        metadata={"source": "gui_bridge", "gui_bridge_request_id": request_id},
        on_activity=on_activity,
    )
    if result.get("status") == "approval_required":
        response = result.get("response")
        if not isinstance(response, PromptResponse):
            response = PromptResponse(
                user_text=f"/shell {command}",
                assistant_text="",
                tool_events=[
                    ToolEvent(
                        name="shell",
                        ok=False,
                        summary="shell approval required",
                        payload={"command": command, "status": "approval_required"},
                    )
                ],
                handled_as_command=True,
            )
        _persist_prompt_response(runtime, response)
        return success(
            request_id=request_id,
            action=action,
            data={
                "accepted": True,
                "approval_required": True,
                "command": command,
                "thread_id": getattr(runtime, "thread_id", None),
                **gui_bridge_payloads_service.prompt_response_payload(
                    response, include_user_text=True
                ),
                "tool_event_count": len(getattr(response, "tool_events", []) or []),
            },
        )

    response = _shell_run_prompt_response(
        command=command,
        result=result,
        activity_events=activity_events,
        item_events=item_events,
    )
    _persist_prompt_response(runtime, response)
    tool_event = response.tool_events[0] if response.tool_events else None
    event_payload = dict(getattr(tool_event, "payload", {}) or {})
    exit_code = event_payload.get("exit_code", event_payload.get("returncode"))
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "approval_required": False,
            "command": command,
            "cwd": event_payload.get("cwd") or _shell_run_cwd(payload),
            "ok": bool(getattr(tool_event, "ok", False)),
            "status": str(event_payload.get("status") or result.get("status") or ""),
            "exit_code": exit_code,
            "stdout": str(event_payload.get("stdout") or ""),
            "stderr": str(event_payload.get("stderr") or ""),
            "duration_ms": event_payload.get("duration_ms"),
            "thread_id": getattr(runtime, "thread_id", None),
            **gui_bridge_payloads_service.prompt_response_payload(response, include_user_text=True),
            "tool_event_count": len(getattr(response, "tool_events", []) or []),
        },
    )


def _shell_run_command(payload: dict[str, Any]) -> str:
    return str(payload.get("command") or payload.get("text") or "").strip()


def _shell_run_cwd(payload: dict[str, Any]) -> str | None:
    cwd = str(payload.get("cwd") or payload.get("workdir") or "").strip()
    return cwd or None


def _payload_optional_text(payload: dict[str, Any], key: str) -> str | None:
    text = str(payload.get(key) or "").strip()
    return text or None


def _payload_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _payload_int(
    payload: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(payload.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _shell_run_timeout_sec(payload: dict[str, Any]) -> int:
    timeout_ms = payload.get("timeout_ms", payload.get("timeoutMs"))
    if timeout_ms is None:
        return _payload_int(payload, "timeout_sec", default=60, minimum=1, maximum=300)
    try:
        value = int(timeout_ms)
    except (TypeError, ValueError):
        value = 60000
    seconds = max(1, (value + 999) // 1000)
    return max(1, min(300, seconds))


def _shell_run_prompt_response(
    *,
    command: str,
    result: dict[str, Any],
    activity_events: list[ActivityEvent],
    item_events: list[dict[str, Any]],
) -> PromptResponse:
    command_result = result.get("command_result")
    tool_events = list(getattr(command_result, "tool_events", []) or [])
    tool_event = result.get("tool_event")
    if isinstance(tool_event, ToolEvent) and tool_event not in tool_events:
        tool_events.insert(0, tool_event)
    if not tool_events:
        tool_events = [
            ToolEvent(
                name="shell",
                ok=False,
                summary="shell command failed",
                payload={"command": command, "status": "error"},
            )
        ]
    primary_event = tool_events[0]
    if not any(item.status in {"ok", "error"} for item in activity_events):
        activity_events.append(
            ActivityEvent(
                title="Shell command completed",
                status="ok" if primary_event.ok else "error",
                detail=primary_event.summary,
                kind="command",
                code="command.run",
                params=command_activity_params({"command": command}),
            )
        )
    response = PromptResponse(
        user_text=f"/shell {command}",
        assistant_text=str(getattr(command_result, "assistant_text", "") or ""),
        commentary_text="",
        tool_events=tool_events,
        activity_events=activity_events,
        handled_as_command=True,
        command_display_text=command,
    )
    response.turn_events = _compose_command_turn_events(
        response,
        item_events=item_events or list(getattr(command_result, "item_events", []) or []),
    )
    return response


def _persist_prompt_response(runtime: Any, response: PromptResponse) -> None:
    thread_store = getattr(runtime, "thread_store", None)
    if thread_store is not None and not getattr(runtime, "thread_id", None):
        starter = getattr(runtime, "start_thread", None)
        if callable(starter):
            starter(cwd=str(getattr(runtime, "cwd", "") or "") or None)
    thread_id = getattr(runtime, "thread_id", None)
    runtime_state = _runtime_state_snapshot(runtime)
    if thread_store is not None and thread_id:
        rollout_item = thread_store.append_turn(
            thread_id,
            response,
            runtime_state=runtime_state,
        )
        appender = getattr(runtime, "_append_rollout_item", None)
        if callable(appender) and isinstance(rollout_item, dict):
            appender(rollout_item)
        return
    appender = getattr(runtime, "_append_history_turn", None)
    if callable(appender):
        appender(_history_turn_payload(response, runtime_state=runtime_state))
