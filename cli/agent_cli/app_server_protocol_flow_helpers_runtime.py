from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import app_server_protocol_turn_flow_runtime as turn_flow_runtime_service
from cli.agent_cli.runtime_core.thread_fork import fork_thread_record


def _emit_invalid_params(server: Any, *, request_id: Any, detail: str) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=-32602,
        message="Invalid params",
        data={"detail": detail},
    )


def _emit_runtime_error(
    server: Any, *, request_id: Any, code: int, message: str, exc: Exception
) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=code,
        message=message,
        data={"detail": f"{type(exc).__name__}: {exc}"},
    )


def handle_thread_read(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    first_text_fn: Callable[..., str],
    thread_helpers: Any,
    reference_thread_payload_fn: Callable[..., dict[str, Any]],
) -> None:
    thread_id = first_text_fn(params, "threadId", "thread_id")
    if not thread_id:
        _emit_invalid_params(
            server, request_id=request_id, detail="params.threadId must be a non-empty string"
        )
        return
    include_turns = bool(params.get("includeTurns", params.get("include_turns", False)))
    try:
        thread = thread_helpers.describe_thread_read(
            server,
            thread_id=thread_id,
            include_turns=include_turns,
        )
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    except Exception as exc:
        thread_helpers.emit_thread_operation_error(
            server,
            request_id=request_id,
            code=-32013,
            message="Thread read failed",
            exc=exc,
        )
        return
    server._emit_result(
        request_id,
        {
            "thread": reference_thread_payload_fn(thread, include_turns=include_turns),
        },
    )


def handle_thread_fork(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    first_text_fn: Callable[..., str],
    thread_helpers: Any,
    reference_thread_payload_fn: Callable[..., dict[str, Any]],
    reference_approval_policy_value_fn: Callable[[Any], Any],
    reference_sandbox_policy_payload_fn: Callable[..., dict[str, Any]],
    reasoning_effort_value_fn: Callable[[Any], Any],
    service_tier_value_fn: Callable[[Any], Any],
) -> None:
    thread_id = first_text_fn(params, "threadId", "thread_id")
    path = first_text_fn(params, "path")
    if not thread_id and not path:
        _emit_invalid_params(
            server,
            request_id=request_id,
            detail="one of params.threadId or params.path must be provided",
        )
        return
    try:
        fork_result = fork_thread_record(
            thread_store=server.runtime.thread_store,
            source_thread_id=thread_id or None,
            source_path=path or None,
            cwd=str(getattr(server.runtime, "cwd", "") or ""),
            provider_status=server.runtime.agent.provider_status(),
            runtime_policy_status=server.runtime.runtime_policy_status(),
            prefer_source_status=True,
            validate_history=True,
        )
        fork_thread_id = str(fork_result.get("thread_id") or "")
        provider_status = dict(fork_result.get("provider_status") or {})
        runtime_policy_status = dict(fork_result.get("runtime_policy_status") or {})
        loaded_payload = server.runtime.resume_thread(fork_thread_id)
        thread = server.runtime.describe_thread(
            thread=dict(loaded_payload.get("thread") or {}),
            status="idle",
            turns=thread_helpers.thread_turns_payload(loaded_payload.get("turns")),
        )
        thread["name"] = None
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    except Exception as exc:
        thread_helpers.emit_thread_operation_error(
            server,
            request_id=request_id,
            code=-32012,
            message="Thread fork failed",
            exc=exc,
        )
        return
    thread_payload = reference_thread_payload_fn(thread, include_turns=True)
    server._emit_result(
        request_id,
        {
            "thread": thread_payload,
            "model": str(
                provider_status.get("provider_model")
                or server.runtime.agent.provider_status().get("provider_model")
                or ""
            ),
            "modelProvider": str(thread_payload.get("modelProvider") or ""),
            "cwd": str(thread_payload.get("cwd") or ""),
            "approvalPolicy": reference_approval_policy_value_fn(
                runtime_policy_status.get("approval_policy")
            ),
            "sandbox": reference_sandbox_policy_payload_fn(
                sandbox_mode=runtime_policy_status.get("sandbox_mode"),
                cwd=str(thread_payload.get("cwd") or ""),
                network_access=runtime_policy_status.get("network_access"),
            ),
            "reasoningEffort": reasoning_effort_value_fn(
                provider_status.get("provider_reasoning_effort")
            ),
            "serviceTier": service_tier_value_fn(provider_status.get("service_tier")),
        },
    )
    server._emit_notification(
        "thread/started",
        {
            "thread": thread_payload,
        },
    )


run_turn_start_job = turn_flow_runtime_service.run_turn_start_job
start_turn_start_job = turn_flow_runtime_service.start_turn_start_job
handle_turn_start = turn_flow_runtime_service.handle_turn_start


def handle_model_list(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    first_text_fn: Callable[..., str],
    parse_cursor_fn: Callable[[Any], int],
    parse_limit_fn: Callable[[dict[str, Any]], int],
    booleanish_fn: Callable[..., bool],
    paginate_items_fn: Callable[..., tuple[list[dict[str, Any]], str | None]],
    catalog_helpers: Any,
    reference_model_list_payload_fn: Callable[..., dict[str, Any]],
) -> None:
    provider_filter = first_text_fn(params, "provider", "modelProvider")
    try:
        cursor = parse_cursor_fn(params.get("cursor"))
        resolved_limit = parse_limit_fn(params)
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    include_hidden = booleanish_fn(
        params.get("includeHidden") if "includeHidden" in params else params.get("include_hidden")
    )
    items = catalog_helpers.available_model_items(
        getattr(server.runtime, "agent", None),
        provider_filter=provider_filter,
        include_hidden=include_hidden,
    )
    page_items, next_cursor = paginate_items_fn(items, cursor=cursor, limit=resolved_limit)
    provider_status = dict(server.runtime.agent.provider_status() or {})
    server._emit_result(
        request_id,
        reference_model_list_payload_fn(
            models=page_items,
            current_model_tokens=catalog_helpers.current_model_tokens(provider_status),
            default_reasoning_effort=str(
                provider_status.get("provider_reasoning_effort") or "medium"
            ),
            next_cursor=next_cursor,
        ),
    )


def handle_mcp_server_status_list(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    parse_cursor_fn: Callable[[Any], int],
    parse_limit_fn: Callable[[dict[str, Any]], int],
    paginate_items_fn: Callable[..., tuple[list[dict[str, Any]], str | None]],
    catalog_helpers: Any,
    runtime_registry_mcp_server_entries_fn: Callable[..., list[dict[str, Any]]],
    reference_mcp_server_status_payload_fn: Callable[..., dict[str, Any]],
) -> None:
    try:
        cursor = parse_cursor_fn(params.get("cursor"))
        resolved_limit = parse_limit_fn(params)
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    tools = getattr(server.runtime, "tools", None)
    plugin_manager = getattr(tools, "_plugin_manager", None)
    entries = runtime_registry_mcp_server_entries_fn(
        plugin_manager,
        runtime_capabilities=catalog_helpers.runtime_capabilities(server.runtime),
    )
    page_entries, next_cursor = paginate_items_fn(entries, cursor=cursor, limit=resolved_limit)
    server._emit_result(
        request_id,
        reference_mcp_server_status_payload_fn(entries=page_entries, next_cursor=next_cursor),
    )


def handle_thread_resume(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    validate_resume_history_fn: Callable[[list[Any]], list[dict[str, Any]]],
    thread_resume_payload_fn: Callable[..., dict[str, Any]],
) -> None:
    history = params.get("history")
    if history is not None and not isinstance(history, list):
        _emit_invalid_params(
            server, request_id=request_id, detail="params.history must be an array when provided"
        )
        return
    validated_history = None
    if history is not None:
        try:
            validated_history = validate_resume_history_fn(history)
        except ValueError as exc:
            _emit_invalid_params(server, request_id=request_id, detail=str(exc))
            return
    path = params.get("path")
    if path is not None and not str(path or "").strip():
        _emit_invalid_params(
            server,
            request_id=request_id,
            detail="params.path must be a non-empty string when provided",
        )
        return
    thread_id = str(params.get("threadId") or "").strip()
    if history is None and path is None and not thread_id:
        _emit_invalid_params(
            server,
            request_id=request_id,
            detail="one of params.history, params.path, or params.threadId must be provided",
        )
        return
    try:
        payload = server.runtime.resume_thread(
            thread_id or None,
            path=str(path or "").strip() or None,
            history=validated_history if history is not None else None,
        )
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    except Exception as exc:
        _emit_runtime_error(
            server,
            request_id=request_id,
            code=-32012,
            message="Thread resume failed",
            exc=exc,
        )
        return
    server._emit_result(
        request_id,
        thread_resume_payload_fn(
            server.runtime,
            payload,
            requested_sources={
                "thread_id": thread_id or None,
                "path": str(path or "").strip() or None,
                "history_count": len(list(history or [])) if history is not None else 0,
            },
        ),
    )


def handle_action_execute(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    action_execute_request_payload_fn: Callable[..., dict[str, Any]],
    first_text_fn: Callable[..., str],
    action_error_cls: type[Exception],
) -> None:
    try:
        request_payload = action_execute_request_payload_fn(
            params,
            first_text_fn=first_text_fn,
        )
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    try:
        result = server.action_worker.execute(request_payload)
    except action_error_cls as exc:
        _emit_runtime_error(
            server,
            request_id=request_id,
            code=-32030,
            message="Action execution failed",
            exc=exc,
        )
        return
    server._emit_result(request_id, {"actionResult": result.to_dict()})


__all__ = [
    "handle_action_execute",
    "handle_mcp_server_status_list",
    "handle_model_list",
    "handle_thread_fork",
    "handle_thread_read",
    "handle_thread_resume",
    "handle_turn_start",
    "run_turn_start_job",
    "start_turn_start_job",
]
