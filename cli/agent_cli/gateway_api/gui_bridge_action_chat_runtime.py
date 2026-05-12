from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.gateway_api import (
    gui_bridge_action_mapping_runtime as gui_bridge_action_mapping_runtime_service,
)
from cli.agent_cli.gateway_api import gui_bridge_payloads as gui_bridge_payloads_service

GuiBridgeResponseBuilder = Callable[..., dict[str, Any]]


def task_run(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    text = gui_bridge_action_mapping_runtime_service.required_payload_text(payload)
    if not text:
        return error(
            request_id=request_id,
            action=action,
            code="task.run.invalid_payload",
            message="text is required",
        )
    response = runtime.handle_prompt(text)
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "thread_id": getattr(runtime, "thread_id", None),
            **gui_bridge_payloads_service.prompt_response_payload(
                response, include_user_text=False
            ),
            "tool_event_count": len(getattr(response, "tool_events", []) or []),
        },
    )


def task_stop(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    requested_task_id = str(payload.get("task_id") or "").strip()
    result = runtime.interrupt_active_run()
    if not result.get("ok"):
        return error(
            request_id=request_id,
            action=action,
            code="task.stop.no_active_run",
            message="no active run to stop",
            detail={
                "task_id": requested_task_id or None,
                "reason": result.get("reason") or "no_active_run",
            },
        )
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "task_id": requested_task_id or result.get("run_token"),
            "interrupted": bool(result.get("interrupted")),
            "already_requested": bool(result.get("already_requested")),
            "run_token": result.get("run_token"),
            "run_label": result.get("run_label"),
        },
    )


def chat_send(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    text = gui_bridge_action_mapping_runtime_service.required_payload_text(payload)
    if not text:
        return error(
            request_id=request_id,
            action=action,
            code="chat.send.invalid_payload",
            message="text is required",
        )
    cwd = _chat_send_cwd(payload)
    if bool(payload.get("new_thread")) or (
        not str(payload.get("thread_id") or "").strip() and not getattr(runtime, "thread_id", None)
    ):
        runtime.start_thread(cwd=cwd)
    elif cwd and not str(payload.get("thread_id") or "").strip():
        runtime.set_cwd(Path(cwd))
    response = runtime.handle_prompt(text)
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "thread_id": getattr(runtime, "thread_id", None),
            "cwd": str(getattr(runtime, "cwd", "") or "") or None,
            "workspaceRoots": _chat_send_workspace_roots(payload, getattr(runtime, "cwd", None)),
            **gui_bridge_payloads_service.prompt_response_payload(response, include_user_text=True),
        },
    )


def _chat_send_cwd(payload: dict[str, Any]) -> str | None:
    cwd = str(payload.get("cwd") or "").strip()
    if cwd:
        return cwd
    workspace_roots = payload.get("workspaceRoots")
    if isinstance(workspace_roots, list):
        for item in workspace_roots:
            text = str(item or "").strip()
            if text:
                return text
    return None


def _chat_send_workspace_roots(payload: dict[str, Any], runtime_cwd: Any) -> list[str]:
    workspace_roots = payload.get("workspaceRoots")
    if isinstance(workspace_roots, list):
        roots = [str(item or "").strip() for item in workspace_roots if str(item or "").strip()]
        if roots:
            return roots
    cwd = str(payload.get("cwd") or runtime_cwd or "").strip()
    return [cwd] if cwd else []
