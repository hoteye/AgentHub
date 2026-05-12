from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_services.delegated_agent_session_payload_pure_helpers_runtime import (
    normalize_async_started_payload,
    normalized_optional_bool,
)


def codex_collab_function_output_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def codex_collab_event_payload(
    payload: dict[str, Any] | None,
    *,
    function_output: Any,
) -> dict[str, Any]:
    result = dict(payload or {})
    result["function_call_output"] = codex_collab_function_output_text(function_output)
    result["function_call_output_model_visible"] = True
    return result


def codex_agent_status_wire(
    *,
    status: Any,
    assistant_text: Any = "",
    error_text: Any = "",
    terminal_reason: Any = "",
) -> Any:
    normalized_status = str(status or "").strip().lower()
    if normalized_status in {"queued", "starting", "idle"}:
        return "pending_init"
    if normalized_status in {"running", "closing"}:
        return "running"
    if normalized_status == "completed":
        message = str(assistant_text or "").strip()
        return {"completed": message or None}
    if normalized_status == "failed":
        error = str(error_text or "").strip() or str(terminal_reason or "").strip() or "errored"
        return {"errored": error}
    if normalized_status == "closed":
        return "shutdown"
    return "not_found"


def codex_agent_status_wire_for_session(session: Any) -> Any:
    return codex_agent_status_wire(
        status=getattr(session, "status", ""),
        assistant_text=getattr(session, "assistant_text", ""),
        error_text=getattr(session, "error", ""),
        terminal_reason=getattr(session, "terminal_reason", ""),
    )


def spawn_agent_arguments(
    *,
    task_text: str,
    role: str,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    effective_async_mode: bool,
    delegation_metadata: dict[str, Any],
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
    source_message: str | None = None,
    codex_collab_payload: bool = False,
) -> dict[str, Any]:
    if codex_collab_payload:
        arguments: dict[str, Any] = {
            **(
                {"message": str(source_message or "").strip()}
                if str(source_message or "").strip()
                else {}
            ),
            **(
                {
                    "items": [
                        dict(item) for item in list(input_items or []) if isinstance(item, dict)
                    ]
                }
                if input_items is not None
                else {}
            ),
            **(
                {"agent_type": str(role or "").strip() or "subagent"}
                if str(role or "").strip()
                else {}
            ),
        }
        if fork_context is not None:
            arguments["fork_context"] = bool(fork_context)
        return arguments
    normalized_wait_required = None
    if "wait_required" in delegation_metadata:
        normalized_wait_required = normalized_optional_bool(
            delegation_metadata.get("wait_required")
        )
    return {
        "task": task_text,
        "role": str(role or "").strip() or "subagent",
        **({"model": str(model).strip()} if str(model or "").strip() else {}),
        **({"provider": str(provider).strip()} if str(provider or "").strip() else {}),
        **(
            {"reasoning_effort": str(reasoning_effort).strip()}
            if str(reasoning_effort or "").strip()
            else {}
        ),
        **({"timeout": int(timeout)} if timeout not in (None, "") else {}),
        **({"async": True} if effective_async_mode else {}),
        **(
            {"reason": delegation_metadata["delegation_reason"]}
            if delegation_metadata.get("delegation_reason")
            else {}
        ),
        **(
            {"mode": delegation_metadata["delegation_mode"]}
            if delegation_metadata.get("delegation_mode")
            else {}
        ),
        **(
            {
                "wait_required": (
                    normalized_wait_required if normalized_wait_required is not None else False
                )
            }
            if "wait_required" in delegation_metadata
            else {}
        ),
        **(
            {"task_shape": delegation_metadata["task_shape"]}
            if delegation_metadata.get("task_shape")
            else {}
        ),
        **(
            {"subagent_type": delegation_metadata["subagent_type"]}
            if delegation_metadata.get("subagent_type")
            else {}
        ),
    }


def session_tool_result(
    *,
    tool_name: str,
    target: str,
    payload: dict[str, Any],
    assistant_text: str,
    summary: str,
    tool_event_factory: Callable[..., Any],
    command_result_factory: Callable[..., Any],
    generic_tool_call_item_events_fn: Callable[..., list[dict[str, Any]]],
) -> Any:
    event = tool_event_factory(
        name=tool_name,
        ok=True,
        summary=summary,
        payload=payload,
    )
    return command_result_factory(
        assistant_text=assistant_text,
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name=tool_name,
            arguments={"target": str(target or "").strip()},
            ok=True,
            summary=summary,
            structured_content=dict(event.payload or {}),
        ),
    )


def codex_collab_tool_result(
    *,
    tool_name: str,
    payload: dict[str, Any],
    function_output: Any,
    assistant_text: str,
    summary: str,
    tool_event_factory: Callable[..., Any],
    command_result_factory: Callable[..., Any],
) -> Any:
    event = tool_event_factory(
        name=tool_name,
        ok=True,
        summary=summary,
        payload=codex_collab_event_payload(
            payload,
            function_output=function_output,
        ),
    )
    return command_result_factory(
        assistant_text=assistant_text,
        tool_events=[event],
        item_events=[],
    )


def async_spawn_result(
    *,
    session: Any,
    task_text: str,
    role: str,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    delegation_metadata: dict[str, Any],
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
    delegated_agent_payload_fn: Callable[[Any], dict[str, Any]],
    tool_event_factory: Callable[..., Any],
    command_result_factory: Callable[..., Any],
    generic_tool_call_item_events_fn: Callable[..., list[dict[str, Any]]],
    codex_collab_payload: bool = False,
) -> Any:
    payload = normalize_async_started_payload(delegated_agent_payload_fn(session))
    if codex_collab_payload:
        return codex_collab_tool_result(
            tool_name="spawn_agent",
            payload=payload,
            function_output={
                "agent_id": str(getattr(session, "agent_id", "") or "").strip(),
                "nickname": None,
            },
            assistant_text=f"delegated agent {session.agent_id} started",
            summary="spawn_agent started",
            tool_event_factory=tool_event_factory,
            command_result_factory=command_result_factory,
        )
    payload["async"] = True
    event = tool_event_factory(
        name="spawn_agent",
        ok=True,
        summary="spawn_agent started",
        payload=payload,
    )
    return command_result_factory(
        assistant_text=f"delegated agent {session.agent_id} started",
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name="spawn_agent",
            arguments=spawn_agent_arguments(
                task_text=task_text,
                role=role,
                model=model,
                provider=provider,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                effective_async_mode=True,
                delegation_metadata=delegation_metadata,
                input_items=input_items,
                fork_context=fork_context,
                source_message=task_text if codex_collab_payload else None,
                codex_collab_payload=codex_collab_payload,
            ),
            ok=True,
            summary="spawn_agent started",
            structured_content=dict(event.payload or {}),
        ),
    )
