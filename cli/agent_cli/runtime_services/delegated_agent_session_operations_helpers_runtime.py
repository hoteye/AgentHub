from __future__ import annotations

from dataclasses import replace
from typing import Any


def sync_delegated_run_record_impl(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    manager = getattr(runtime, "run_manager", None)
    if manager is None:
        return
    agent_id = str(getattr(session, "agent_id", "") or "").strip()
    protocol_run_id = str(getattr(session, "protocol_run_id", "") or "").strip()
    run_id = protocol_run_id or f"delegated:{agent_id or 'unknown'}"
    if not run_id:
        return
    role = str(getattr(session, "role", "") or "").strip().lower()
    delegation_mode = str(getattr(session, "delegation_mode", "") or "").strip().lower()
    kind = "background" if role == "teammate" and delegation_mode == "background" else "task"
    parent_run_id = str(getattr(session, "protocol_parent_run_id", "") or "").strip()
    thread_id = (
        str(getattr(session, "protocol_thread_id", "") or "").strip()
        or str(getattr(runtime, "thread_id", "") or "").strip()
    )
    status = str(forced_status or "").strip().lower()
    if not status:
        session_status = str(getattr(session, "status", "") or "").strip().lower()
        terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip().lower()
        if session_status in {"running", "starting"}:
            status = "running"
        elif session_status == "failed":
            status = "failed"
        elif session_status == "completed":
            status = "completed"
        elif session_status == "closed":
            if terminal_reason in {"failed"}:
                status = "failed"
            elif terminal_reason in {"completed"}:
                status = "completed"
            else:
                status = "cancelled"
        else:
            status = "created"
    summary = str(forced_summary or "").strip() or f"delegated session {status}"
    payload = {
        "agent_id": agent_id,
        "role": str(getattr(session, "role", "") or "").strip(),
        "session_status": str(getattr(session, "status", "") or "").strip(),
        "terminal_reason": str(getattr(session, "terminal_reason", "") or "").strip(),
        "delegation_mode": str(getattr(session, "delegation_mode", "") or "").strip(),
    }
    if manager.get(run_id) is None:
        try:
            manager.create(
                run_id=run_id,
                kind=kind,
                thread_id=thread_id,
                parent_run_id=parent_run_id,
                summary="delegated session created",
                payload=payload,
            )
        except Exception:
            return
    try:
        manager.update(
            run_id,
            status=status,
            summary=summary,
            payload=payload,
        )
    except Exception:
        return


def provider_config_with_model_timeout_impl(config: Any, timeout: int | None) -> Any:
    if not isinstance(timeout, int) or timeout <= 0:
        return config
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    raw_model["model_timeout"] = timeout
    try:
        return replace(config, raw_model=raw_model)
    except Exception:
        return config


def delegated_planner_impl(
    runtime: Any,
    config: Any,
    *,
    timeout: int | None = None,
    build_planner_fn: Any,
    current_host_platform_fn: Any,
    provider_config_with_model_timeout_fn: Any,
) -> Any:
    resolved_config = provider_config_with_model_timeout_fn(config, timeout)
    planner = build_planner_fn(
        resolved_config,
        host_platform=getattr(runtime.agent, "host_platform", None) or current_host_platform_fn(),
        cwd=runtime.cwd,
        plugin_manager_factory=getattr(runtime.agent, "_plugin_manager_factory", None),
    )
    if isinstance(timeout, int) and timeout > 0:
        client = getattr(planner, "client", None)
        with_options = getattr(client, "with_options", None)
        if callable(with_options):
            try:
                planner.client = with_options(timeout=timeout)
            except Exception:
                pass
    return planner
