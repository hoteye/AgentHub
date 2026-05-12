from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_core.thread_session import validate_resume_history


def _clear_active_thread_id(thread_store: Any) -> None:
    lock = getattr(thread_store, "_lock", None)
    connection = getattr(thread_store, "_connection", None)
    if lock is None or not callable(connection):
        return
    with lock, connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'active_thread_id'")
        conn.commit()


def _thread_path_exists(thread: dict[str, Any]) -> bool:
    path_text = str(thread.get("path") or "").strip()
    if not path_text:
        return False
    try:
        return Path(path_text).exists()
    except OSError:
        return False


def resume_payload_preserving_active_thread(
    thread_store: Any,
    *,
    thread_id: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    if thread_store is None:
        raise RuntimeError("thread store not configured")
    get_active = getattr(thread_store, "get_active_thread_id", None)
    restore_active = callable(get_active)
    active_thread_id = get_active() if callable(get_active) else None
    try:
        normalized_path = str(path or "").strip()
        if normalized_path:
            return thread_store.resume_thread_from_path(normalized_path)
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            raise ValueError("thread_id is required when path is absent")
        return thread_store.resume_thread(normalized_thread_id)
    finally:
        if restore_active:
            if active_thread_id:
                thread_store.set_active_thread_id(active_thread_id)
            else:
                _clear_active_thread_id(thread_store)


def fork_source_inputs(
    source_payload: dict[str, Any],
    *,
    validate_history: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    source_thread = dict(source_payload.get("thread") or {})
    rollout_items = [
        {**dict(item), "thread_id": ""}
        for item in list(source_payload.get("rollout_items") or [])
        if isinstance(item, dict) and str(item.get("item_type") or "").strip() != "thread_meta"
    ]
    history = [
        dict(item)
        for item in list(source_payload.get("planner_input_items") or [])
        if isinstance(item, dict)
    ]
    if not rollout_items and not history:
        fallback_history = [
            dict(item)
            for item in list(source_payload.get("history") or [])
            if isinstance(item, dict)
        ]
        history = (
            validate_resume_history(fallback_history) if validate_history else fallback_history
        )
    return source_thread, rollout_items, history


def ensure_fork_source_available(
    *,
    source_rollout_items: list[dict[str, Any]],
    source_history: list[dict[str, Any]],
    source_thread: dict[str, Any],
    source_label: str = "",
) -> None:
    if source_rollout_items or source_history or _thread_path_exists(source_thread):
        return
    label = str(source_label or source_thread.get("thread_id") or "").strip()
    raise ValueError(f"no rollout found for thread id `{label}`")


def fork_thread_status_context(
    source_thread: dict[str, Any],
    *,
    provider_status: dict[str, Any] | None = None,
    runtime_policy_status: dict[str, Any] | None = None,
    prefer_source_status: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = dict(source_thread.get("metadata") or {})
    source_provider_status = dict(metadata.get("provider_status") or {})
    source_runtime_policy = dict(metadata.get("runtime_policy") or {})
    fallback_provider_status = dict(provider_status or {})
    fallback_runtime_policy = dict(runtime_policy_status or {})
    if prefer_source_status:
        return (
            source_provider_status or fallback_provider_status,
            source_runtime_policy or fallback_runtime_policy,
        )
    return (
        fallback_provider_status or source_provider_status,
        fallback_runtime_policy or source_runtime_policy,
    )


def fork_thread_record(
    *,
    thread_store: Any,
    source_thread_id: str | None = None,
    source_path: str | None = None,
    source_payload: dict[str, Any] | None = None,
    cwd: str | None = None,
    provider_status: dict[str, Any] | None = None,
    runtime_policy_status: dict[str, Any] | None = None,
    prefer_source_status: bool = True,
    validate_source: bool = True,
    validate_history: bool = False,
) -> dict[str, Any]:
    if thread_store is None:
        raise RuntimeError("thread store not configured")
    loaded_source_payload = (
        dict(source_payload)
        if source_payload is not None
        else resume_payload_preserving_active_thread(
            thread_store,
            thread_id=source_thread_id,
            path=source_path,
        )
    )
    source_thread, source_rollout_items, source_history = fork_source_inputs(
        loaded_source_payload,
        validate_history=validate_history,
    )
    if validate_source:
        ensure_fork_source_available(
            source_rollout_items=source_rollout_items,
            source_history=source_history,
            source_thread=source_thread,
            source_label=str(source_thread_id or ""),
        )

    effective_provider_status, effective_runtime_policy_status = fork_thread_status_context(
        source_thread,
        provider_status=provider_status,
        runtime_policy_status=runtime_policy_status,
        prefer_source_status=prefer_source_status,
    )
    fork_cwd = str(source_thread.get("cwd") or cwd or "").strip() or None
    if source_rollout_items:
        record = thread_store.start_thread(
            cwd=fork_cwd,
            provider_status=effective_provider_status,
            runtime_policy_status=effective_runtime_policy_status,
        )
        fork_thread_id = str(getattr(record, "thread_id", "") or "")
        copied_rollout_items = [
            {**item, "thread_id": fork_thread_id} for item in source_rollout_items
        ]
        appended_rollout_items = thread_store.append_rollout_items(
            fork_thread_id,
            copied_rollout_items,
        )
        loaded_payload = thread_store.resume_thread(fork_thread_id)
        created_from = "rollout"
    else:
        appended_rollout_items = []
        loaded_payload = thread_store.resume_thread_from_history(
            source_history,
            cwd=fork_cwd,
            provider_status=effective_provider_status,
            runtime_policy_status=effective_runtime_policy_status,
        )
        fork_thread_id = str(dict(loaded_payload.get("thread") or {}).get("thread_id") or "")
        created_from = "history"

    return {
        "thread_id": fork_thread_id,
        "source_thread": source_thread,
        "rollout_items": source_rollout_items,
        "history": source_history,
        "created_from": created_from,
        "loaded_payload": loaded_payload,
        "copied_rollout_items": appended_rollout_items,
        "provider_status": effective_provider_status,
        "runtime_policy_status": effective_runtime_policy_status,
    }
