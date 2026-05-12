from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.runtime_services import (
    delegated_agent_background_runtime_helpers as runtime_helpers,
    delegated_agent_background_state_transition_runtime as background_state_transition_runtime,
)

_ORPHAN_TERMINAL_REASONS = {"orphan_cleanup", "restore_resolution_failed", "role_override_changed"}


def background_task_adapter(
    runtime: Any,
    *,
    build_background_task_adapter_fn: Callable[..., Any],
) -> Any:
    current_cwd = str(runtime.cwd or "").strip()
    if runtime._background_task_adapter_cache is not None and runtime._background_task_adapter_cwd == current_cwd:
        return runtime._background_task_adapter_cache
    adapter = build_background_task_adapter_fn(cwd=runtime.cwd)
    runtime._background_task_adapter_cache = adapter
    runtime._background_task_adapter_cwd = current_cwd
    return adapter


def background_task_adapter_if_enabled(runtime: Any) -> Any | None:
    try:
        adapter = runtime._background_task_adapter()
    except Exception:
        return None
    return adapter if bool(getattr(adapter.config, "enabled", False)) else None


def delegated_background_task_id(session: Any) -> str:
    return f"bg_delegate_{session.agent_id}"


def delegated_background_task_status(status: str, *, has_text: bool, terminal_reason: str = "") -> str:
    return background_state_transition_runtime.delegated_background_task_status(
        status,
        has_text=has_text,
        terminal_reason=terminal_reason,
    )


def delegated_background_notification_state(
    *,
    status: str,
    adopted: bool,
    terminal_reason: str,
) -> str:
    normalized_reason = str(terminal_reason or "").strip().lower()
    if normalized_reason in _ORPHAN_TERMINAL_REASONS:
        return "orphaned"
    return background_state_transition_runtime.delegated_background_notification_state(
        status=status,
        adopted=adopted,
        terminal_reason=terminal_reason,
    )


def delegated_orphan_cleanup_candidate(
    *,
    status: Any,
    queued_inputs: List[Dict[str, Any]] | None = None,
    active_input: Dict[str, Any] | None = None,
) -> bool:
    return background_state_transition_runtime.delegated_orphan_cleanup_candidate(
        status=status,
        queued_inputs=queued_inputs,
        active_input=active_input,
    )


def _sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    runtime_helpers.sync_delegated_run_record(
        runtime,
        session,
        forced_status=forced_status,
        forced_summary=forced_summary,
    )


def sync_delegated_background_task(
    runtime: Any,
    session: Any,
    *,
    preview_text_fn: Callable[..., str],
) -> None:
    runtime_helpers.sync_delegated_background_task(
        runtime,
        session,
        preview_text_fn=preview_text_fn,
    )


def record_orphaned_delegated_background_task(
    runtime: Any,
    raw_session: Dict[str, Any],
    *,
    reason: str,
    error: str = "",
    preview_text_fn: Callable[..., str],
    now_iso_fn: Callable[[], str],
) -> None:
    runtime_helpers.record_orphaned_delegated_background_task(
        runtime,
        raw_session,
        reason=reason,
        error=error,
        preview_text_fn=preview_text_fn,
        now_iso_fn=now_iso_fn,
    )


def request_delegated_session_cleanup(
    runtime: Any,
    session: Any,
    *,
    reason: str,
    summary: str,
    now_iso_fn: Callable[[], str],
) -> bool:
    with session.condition:
        outcome = background_state_transition_runtime.request_session_cleanup(
            session=session,
            reason=reason,
            summary=summary,
            now_iso_fn=now_iso_fn,
            refresh_current_step_id_fn=runtime._refresh_delegated_current_step_id,
            record_checkpoint_fn=runtime._record_delegated_checkpoint,
        )
        if not outcome["changed"]:
            return False
        session.condition.notify_all()
    runtime._sync_delegated_background_task(session)
    _sync_delegated_run_record(
        runtime,
        session,
        forced_status="cancelled",
        forced_summary=f"delegated session cleanup: {reason}",
    )
    runtime._notify_delegated_scheduler()
    return True


def cleanup_delegated_sessions_for_role(runtime: Any, role_name: str, *, reason: str) -> int:
    return runtime_helpers.cleanup_delegated_sessions_for_role(runtime, role_name, reason=reason)


def snapshot_delegated_agent_session(runtime: Any, session: Any) -> Dict[str, Any]:
    return runtime_helpers.snapshot_delegated_agent_session(runtime, session)


def delegated_agent_state_snapshot(runtime: Any) -> List[Dict[str, Any]]:
    return runtime_helpers.delegated_agent_state_snapshot(runtime)


def restored_delegated_status(
    *,
    status: Any,
    queued_inputs: List[Dict[str, Any]],
    close_requested: bool,
    closed: bool,
    assistant_text: str,
    error: str,
) -> str:
    return background_state_transition_runtime.restored_delegated_status(
        status=status,
        queued_inputs=queued_inputs,
        close_requested=close_requested,
        closed=closed,
        assistant_text=assistant_text,
        error=error,
    )


def reset_delegated_agent_state(runtime: Any) -> None:
    runtime_helpers.reset_delegated_agent_state(runtime)


def restore_delegated_agent_state(
    runtime: Any,
    state: Dict[str, Any],
    *,
    session_class: Any,
    now_iso_fn: Callable[[], str],
) -> None:
    runtime_helpers.restore_delegated_agent_state(
        runtime,
        state,
        session_class=session_class,
        now_iso_fn=now_iso_fn,
    )
