from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cli.agent_cli.gateway_api import (
    gui_bridge_action_mapping_runtime as gui_bridge_action_mapping_runtime_service,
)
from cli.agent_cli.gateway_api import gui_bridge_payloads as gui_bridge_payloads_service
from cli.agent_cli.models import PromptResponse

GuiBridgeResponseBuilder = Callable[..., dict[str, Any]]


def thread_list(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    limit = gui_bridge_action_mapping_runtime_service.payload_limit(payload, default=20)
    cwd = str(payload.get("cwd") or "").strip() or None
    threads = runtime.list_threads(limit=limit, cwd=cwd)
    loaded_thread_id = getattr(runtime, "thread_id", None)
    active_thread_id = loaded_thread_id
    if not active_thread_id:
        thread_store = getattr(runtime, "thread_store", None)
        if thread_store is not None:
            getter = getattr(thread_store, "get_active_thread_id", None)
            if callable(getter):
                active_thread_id = getter()
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_action_mapping_runtime_service.thread_list_payload(
            threads,
            loaded_thread_id=loaded_thread_id,
            active_thread_id=active_thread_id,
            describe_thread_fn=runtime.describe_thread,
        ),
    )


def thread_resume(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    thread_id = str(payload.get("thread_id") or "").strip()
    if not thread_id:
        return error(
            request_id=request_id,
            action=action,
            code="thread.resume.invalid_payload",
            message="thread_id is required",
        )
    resumed = runtime.resume_thread(thread_id)
    thread = runtime.describe_thread(
        dict(resumed.get("thread") or {}),
        status="idle",
        turns=[dict(item) for item in list(resumed.get("turns") or []) if isinstance(item, dict)],
    )
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_action_mapping_runtime_service.thread_resume_payload(
            resumed=resumed,
            thread=thread,
            thread_id=thread_id,
            thread_history_turn_payload_fn=gui_bridge_payloads_service.thread_history_turn_payload,
            runtime_snapshot=runtime.response_runtime_snapshot(),
        ),
    )


def _runtime_state_snapshot(runtime: Any) -> dict[str, Any]:
    snapshotter = getattr(runtime, "_snapshot_thread_state", None)
    if callable(snapshotter):
        return dict(snapshotter() or {})
    snapshotter = getattr(runtime, "response_runtime_snapshot", None)
    if callable(snapshotter):
        return dict(snapshotter() or {})
    return {}


def _history_turn_payload(
    response: PromptResponse, *, runtime_state: dict[str, Any]
) -> dict[str, Any]:
    return {
        "turn_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "user_text": response.user_text,
        "commentary_text": response.commentary_text,
        "assistant_text": response.assistant_text,
        "command_display_text": response.command_display_text,
        "assistant_history_text": response.assistant_text,
        "response_items": [item.to_dict() for item in list(response.response_items or [])],
        "handled_as_command": response.handled_as_command,
        "status": dict(response.status or {}),
        "protocol_diagnostics": dict(response.protocol_diagnostics or {}),
        "runtime_state": runtime_state,
        "attachments": [item.to_dict() for item in list(response.attachments or [])],
        "tool_events": [item.to_dict() for item in list(response.tool_events or [])],
        "activity_events": [item.to_dict() for item in list(response.activity_events or [])],
        "reference_context_items": [
            item.to_dict() for item in list(response.reference_context_items or [])
        ],
        "turn_events": [
            dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)
        ],
    }
