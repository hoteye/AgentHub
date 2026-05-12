from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.thread_fork import (
    ensure_fork_source_available,
    fork_source_inputs,
    fork_thread_status_context,
    resume_payload_preserving_active_thread,
)


def thread_store_resume_payload_preserving_active_thread(
    server: Any,
    *,
    thread_id: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    thread_store = getattr(server.runtime, "thread_store", None)
    return resume_payload_preserving_active_thread(
        thread_store,
        thread_id=thread_id,
        path=path,
    )


def thread_read_status(server: Any, *, thread_id: str) -> str:
    loaded_thread_id = str(getattr(server.runtime, "thread_id", "") or "").strip()
    return "idle" if loaded_thread_id and loaded_thread_id == thread_id else "not_loaded"


def emit_thread_operation_error(
    server: Any,
    *,
    request_id: Any,
    code: int,
    message: str,
    exc: Exception,
) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=code,
        message=message,
        data={"detail": f"{type(exc).__name__}: {exc}"},
    )


def thread_turns_payload(items: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(items or []) if isinstance(item, dict)]


def describe_thread_read(
    server: Any,
    *,
    thread_id: str,
    include_turns: bool,
) -> dict[str, Any]:
    status = thread_read_status(server, thread_id=thread_id)
    if not include_turns:
        return server.runtime.describe_thread(
            thread_id=thread_id,
            status=status,
            turns=[],
        )
    payload = thread_store_resume_payload_preserving_active_thread(server, thread_id=thread_id)
    return server.runtime.describe_thread(
        thread=dict(payload.get("thread") or {}),
        status=status,
        turns=thread_turns_payload(payload.get("turns")),
    )


def thread_fork_source_inputs(
    source_payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    return fork_source_inputs(source_payload, validate_history=True)


def ensure_thread_fork_source_available(
    *,
    source_rollout_items: list[dict[str, Any]],
    source_history: list[dict[str, Any]],
    source_thread: dict[str, Any],
    thread_id: str,
) -> None:
    ensure_fork_source_available(
        source_rollout_items=source_rollout_items,
        source_history=source_history,
        source_thread=source_thread,
        source_label=thread_id or str(source_thread.get("thread_id") or ""),
    )


def thread_fork_status_context(
    server: Any,
    *,
    source_thread: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return fork_thread_status_context(
        source_thread,
        provider_status=server.runtime.agent.provider_status(),
        runtime_policy_status=server.runtime.runtime_policy_status(),
        prefer_source_status=True,
    )
