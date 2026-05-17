from __future__ import annotations

import asyncio
from typing import Any

from cli.agent_cli import update_runtime
from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui.status_indicator import ANIMATION_INTERVAL_SECONDS


def _start_tab_workers(mgr: Any) -> None:
    for tab_id in list(getattr(mgr, "_tab_order", []) or []):
        session = mgr.get(tab_id)
        if session is not None and (
            session.request_worker_task is None or session.request_worker_task.done()
        ):
            mgr._start_worker_task(tab_id)


def _startup_provider_status(app: Any) -> dict[str, Any]:
    runtime = getattr(app, "runtime", None)
    agent = getattr(runtime, "agent", None)
    provider_status = getattr(agent, "provider_status", None)
    return dict(provider_status() or {}) if callable(provider_status) else {}


def _startup_setup_required(status: dict[str, Any]) -> bool:
    provider_ready = str(status.get("provider_ready") or "").strip().lower()
    provider_source = str(status.get("provider_source") or "").strip().lower()
    provider_name = str(status.get("provider_name") or "").strip().lower()
    provider_auth_ready = str(status.get("provider_auth_ready") or "").strip().lower()
    provider_status_state = str(status.get("provider_status_state") or "").strip().lower()
    auth_status = str(status.get("auth_status") or "").strip().lower()
    hard_unavailable = str(status.get("provider_hard_unavailable") or "").strip().lower()
    if provider_source == "fallback" or provider_name == "fallback":
        return False
    if provider_ready != "true" and provider_source in {"", "-", "not_configured"}:
        return True
    if provider_auth_ready == "false":
        return True
    if provider_status_state == "auth_blocked":
        return True
    if hard_unavailable == "true" or provider_status_state == "hard_unavailable":
        return True
    return auth_status == "missing"


def _startup_setup_payload(status: dict[str, Any]) -> dict[str, str]:
    provider = str(
        status.get("provider_name") or status.get("provider_public_name") or "openai"
    ).strip()
    if provider in {"", "-"}:
        provider = "openai"
    base_url = str(status.get("provider_base_url") or "").strip()
    if base_url == "-":
        base_url = ""
    return {"provider": provider, "base_url": base_url}


def _startup_setup_notice(app: Any) -> str | None:
    if list(getattr(app, "_transcript_entries", []) or []):
        return None
    status = _startup_provider_status(app)
    if not _startup_setup_required(status):
        return None
    return "No provider configured. Run /setup to add API key and optional base URL."


def _startup_update_notice(app: Any, *, setup_required: bool) -> str | None:
    if setup_required:
        return None
    if list(getattr(app, "_transcript_entries", []) or []):
        return None
    try:
        return update_runtime.cached_update_notice() or None
    except Exception:
        return None


def _present_startup_setup_overlay(app: Any, payload: dict[str, str]) -> bool:
    try:
        from cli.agent_cli.ui.setup_modal import present_setup_overlay, setup_command_from_payload
    except Exception:
        return False

    def _on_submit(submitted: dict[str, str]) -> None:
        command_text = setup_command_from_payload(submitted)
        app._write_system_notice("Running setup...")
        asyncio.create_task(app._enqueue_runtime_request(command_text, [], priority="later"))

    try:
        return present_setup_overlay(
            app=app,
            payload=payload,
            on_submit=_on_submit,
            on_cancel=lambda: None,
        )
    except Exception:
        return False


def _write_startup_provider_notices(app: Any) -> tuple[dict[str, Any], bool]:
    startup_status = _startup_provider_status(app)
    startup_notice = _startup_setup_notice(app)
    startup_setup_required = bool(startup_notice and _startup_setup_required(startup_status))
    if startup_notice:
        app._write_system_notice(startup_notice)
    startup_update_notice = _startup_update_notice(app, setup_required=startup_setup_required)
    if startup_update_notice:
        app._write_system_notice(startup_update_notice)
    return startup_status, startup_setup_required


def _schedule_startup_setup_overlay(
    app: Any,
    *,
    startup_status: dict[str, Any],
    startup_setup_required: bool,
) -> None:
    if not startup_setup_required:
        return
    startup_setup_payload = _startup_setup_payload(startup_status)

    def _present_startup_setup() -> None:
        _present_startup_setup_overlay(app, startup_setup_payload)

    app.call_after_refresh(_present_startup_setup)


def on_mount(app: Any) -> None:
    startup_log("app.on_mount.begin")
    app._install_local_request_user_input_handler()
    mgr = getattr(app, "_tab_manager", None)
    if mgr is not None:
        _start_tab_workers(mgr)
        if bool(getattr(app, "_tab_manifest_restored", False)):
            mgr._restore_tab_state(mgr.active_tab_id)
        mgr._start_scroll_capture_timer()
    else:
        if app._request_worker_task is None or app._request_worker_task.done():
            app._request_worker_task = asyncio.create_task(app._request_worker_loop())
    app._apply_layout_state(max(1, app.size.width))
    if not bool(getattr(app, "_tab_manifest_restored", False)):
        app._restore_transcript_from_runtime_history()
    if mgr is not None:
        manifest_notice = getattr(mgr, "pop_manifest_restore_notice", lambda: None)()
        if manifest_notice:
            key, params = manifest_notice
            app._write_system_notice(app._t(key, **params))
    startup_status, startup_setup_required = _write_startup_provider_notices(app)
    update_runtime.schedule_background_update_check()
    app._focus_input()
    _schedule_startup_setup_overlay(
        app,
        startup_status=startup_status,
        startup_setup_required=startup_setup_required,
    )
    app.call_after_refresh(app._stabilize_initial_frame)
    app.set_timer(0.05, app._stabilize_initial_frame)
    app.set_timer(0.2, app._stabilize_initial_frame)
    app._prompt_burst_timer = app.set_interval(0.02, app._flush_prompt_composer_burst_if_due)
    app._dynamic_hint_timer = app.set_interval(
        ANIMATION_INTERVAL_SECONDS,
        app._refresh_dynamic_hint,
    )
    startup_log("app.on_mount.end")
