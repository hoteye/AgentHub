from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from textual.css.query import NoMatches

from cli.agent_cli import update_runtime
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui.status_indicator import ANIMATION_INTERVAL_SECONDS


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


def on_mount(app: Any) -> None:
    startup_log("app.on_mount.begin")
    app._install_local_request_user_input_handler()
    mgr = getattr(app, "_tab_manager", None)
    if mgr is not None:
        for tab_id in list(getattr(mgr, "_tab_order", []) or []):
            session = mgr.get(tab_id)
            if session is not None and (
                session.request_worker_task is None or session.request_worker_task.done()
            ):
                mgr._start_worker_task(tab_id)
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
    startup_status = _startup_provider_status(app)
    startup_notice = _startup_setup_notice(app)
    startup_setup_required = bool(startup_notice and _startup_setup_required(startup_status))
    if startup_notice:
        app._write_system_notice(startup_notice)
    startup_update_notice = _startup_update_notice(app, setup_required=startup_setup_required)
    if startup_update_notice:
        app._write_system_notice(startup_update_notice)
    update_runtime.schedule_background_update_check()
    app._focus_input()
    if startup_setup_required:
        startup_setup_payload = _startup_setup_payload(startup_status)

        def _present_startup_setup() -> None:
            _present_startup_setup_overlay(app, startup_setup_payload)

        app.call_after_refresh(_present_startup_setup)
    app.call_after_refresh(app._stabilize_initial_frame)
    app.set_timer(0.05, app._stabilize_initial_frame)
    app.set_timer(0.2, app._stabilize_initial_frame)
    app._prompt_burst_timer = app.set_interval(0.02, app._flush_prompt_composer_burst_if_due)
    app._dynamic_hint_timer = app.set_interval(
        ANIMATION_INTERVAL_SECONDS,
        app._refresh_dynamic_hint,
    )
    startup_log("app.on_mount.end")


def on_key(app: Any, event: Any) -> None:
    if app._screen_mode == "transcript":
        if app._handle_transcript_search_key(event.key):
            event.stop()
            event.prevent_default()
            return
        character = str(getattr(event, "character", "") or "")
        if character and app._handle_transcript_search_text_input(character):
            event.stop()
            event.prevent_default()
            return
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            app.action_toggle_transcript()
            return
        if event.key == "q":
            event.stop()
            event.prevent_default()
            app.action_toggle_transcript()
            return
        if app._handle_transcript_navigation_key(event.key):
            event.stop()
            event.prevent_default()
            return
    if event.key == "ctrl+c":
        event.stop()
        event.prevent_default()
        app.action_ctrl_c()
        return
    if event.key == "escape" and app.handle_escape_key():
        event.stop()
        event.prevent_default()


def on_mouse_down(app: Any, event: Any) -> None:
    button = getattr(event, "button", None)
    if button == 3:
        if _copy_active_selection_to_clipboard(app):
            try:
                app._arm_prompt_paste_suppression()
            except Exception:
                pass
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
            return
        if app.paste_prompt_from_clipboard(
            report_empty=False,
            suppress_following_native_paste=True,
        ):
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
        return
    if button != 1:
        return
    if _switch_tab_from_rail_screen_position(app, event):
        event.stop()
        event.prevent_default()
        return


def on_mouse_up(app: Any, event: Any) -> None:
    record_idle_mouse_position(app, event)
    if event.button not in {1, 3}:
        return
    if event.button == 1 and _switch_tab_from_rail_screen_position(app, event):
        event.stop()
        event.prevent_default()
        return
    if app._event_targets_prompt_composer(event):
        return
    if app._event_targets_active_overlay(event):
        return
    app.call_after_refresh(app._focus_input)


def on_mouse_move(app: Any, event: Any) -> None:
    record_idle_mouse_position(app, event)


def _switch_tab_from_rail_screen_position(app: Any, event: Any) -> bool:
    try:
        from cli.agent_cli.ui.tab_bar import TabBar
    except Exception:
        return False
    try:
        tab_bar = app.query_one("#tab_bar", TabBar)
    except Exception:
        return False
    if getattr(tab_bar, "orientation", "") != "vertical":
        return False
    screen_x = getattr(event, "screen_x", None)
    screen_y = getattr(event, "screen_y", None)
    if screen_x is None or screen_y is None:
        return False
    region = getattr(tab_bar, "region", None)
    if region is None:
        return False
    try:
        x = int(screen_x) - int(region.x)
        y = int(screen_y) - int(region.y)
        width = int(region.width)
        height = int(region.height)
    except Exception:
        return False
    if x < 0 or y < 0 or x >= width or y >= height:
        return False
    spans = list(getattr(tab_bar, "_tab_spans", []) or [])
    if not spans:
        try:
            tab_bar.render()
        except Exception:
            return False
        spans = list(getattr(tab_bar, "_tab_spans", []) or [])
    for tab_id, start_y, end_y in spans:
        if start_y <= y < end_y:
            mgr = getattr(app, "_tab_manager", None)
            if mgr is None or tab_id == getattr(mgr, "active_tab_id", None):
                return True
            if mgr.switch_to_tab(tab_id):
                app._refresh_top_title_bar()
                app._focus_input()
            return True
    return False


def _copy_active_selection_to_clipboard(app: Any) -> bool:
    if _copy_transcript_selection_to_clipboard(app):
        return True
    return _copy_composer_selection_to_clipboard(app)


def _copy_transcript_selection_to_clipboard(app: Any) -> bool:
    try:
        from textual.document._document import Selection

        from cli.agent_cli.ui.widgets import TranscriptArea

        transcript = app.query_one("#main_log", TranscriptArea)
        selected_text = str(getattr(transcript, "selected_text", "") or "").strip()
        if not selected_text:
            return False
        transcript.app.copy_to_clipboard(selected_text)
        transcript.selection = Selection.cursor(transcript.selection.end)
        transcript._last_right_click_copied_text = selected_text
        return True
    except Exception:
        return False


def _copy_composer_selection_to_clipboard(app: Any) -> bool:
    try:
        from cli.agent_cli.ui.composer import PromptComposer

        composer = app.query_one("#prompt_composer", PromptComposer)
    except Exception:
        return False
    if not bool(getattr(composer, "has_selection", False)):
        return False
    try:
        copied = bool(composer.copy_selection_to_clipboard())
        if copied:
            composer.clear_selection()
        return copied
    except Exception:
        return False


def record_idle_mouse_position(app: Any, event: Any) -> None:
    if not app._presentation.idle_cat_enabled:
        return
    if app._idle_status_started_at is None:
        return
    current_time = monotonic()
    if current_time - app._idle_status_started_at < app.IDLE_STATUS_DELAY_SECONDS:
        return
    mouse_x = getattr(event, "screen_x", None)
    if mouse_x is None:
        mouse_x = getattr(event, "x", None)
    if mouse_x is None:
        return
    interaction_triggered = app._idle_cat_animator.observe_mouse(
        x=int(mouse_x),
        width=max(1, int(app.size.width)),
        now=current_time,
    )
    if not interaction_triggered:
        return
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return


def action_ctrl_c(app: Any) -> None:
    startup_log(
        "app.action_ctrl_c "
        f"busy={app._busy} "
        f"interruptible={app._has_interruptible_run()} "
        f"has_prompt={bool(app._current_prompt_text())} "
        f"quit_armed={app._quit_shortcut_active()}"
    )
    if app._quit_shortcut_active():
        app._quit_shortcut_expires_at = None
        app._populate_exit_request_from_runtime()
        app._begin_shutdown()
        app.exit()
        return
    if app._has_interruptible_run():
        app._arm_quit_shortcut()
        app.action_interrupt_run()
        return
    app._flush_prompt_composer_burst()
    if app._current_prompt_text():
        app._clear_prompt_text()
        app._refresh_prompt_composer()
        app._focus_input()
    app._arm_quit_shortcut()


def action_interrupt_run(app: Any) -> None:
    if timeline_debug_enabled():
        log_timeline(
            "ui.interrupt.requested",
            busy=app._busy,
            focus_id=getattr(getattr(app, "focused", None), "id", None),
            queue_size=app._request_queue.qsize(),
            queued_run_labels=list(app._queued_run_labels),
        )
    optimistic_interrupt = app._has_interruptible_run()
    if optimistic_interrupt:
        app._mark_live_turn_interrupt_requested()
    result = app.runtime.interrupt_active_run()
    if timeline_debug_enabled():
        log_timeline(
            "ui.interrupt.result",
            busy=app._busy,
            result=dict(result or {}),
        )
    if result.get("ok"):
        if optimistic_interrupt:
            app._render_live_interrupt_notice()
        if app._busy:
            app._set_busy(False)
    elif optimistic_interrupt and not app._runtime_has_active_run():
        app._live_turn_interrupt_requested = False
    app._focus_input()


def handle_escape_key(app: Any) -> bool:
    if app._screen_mode == "transcript":
        app.action_toggle_transcript()
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="exit_transcript", busy=app._busy)
        return True
    if bool(getattr(app, "_shortcut_overlay_active", False)):
        app._clear_shortcut_overlay()
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="shortcut_overlay", busy=app._busy)
        return True
    cancel_approval_overlay = getattr(app, "_cancel_approval_overlay_on_escape", None)
    if callable(cancel_approval_overlay) and cancel_approval_overlay():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="approval_overlay_cancel", busy=app._busy)
        return True
    if app._cancel_request_user_input_on_escape():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="request_user_input_cancel", busy=app._busy)
        return True
    if app.dismiss_slash_popup():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="dismiss_popup", busy=app._busy)
        return True
    if app.handle_escape_interrupt():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="interrupt", busy=app._busy)
        return True
    if timeline_debug_enabled():
        log_timeline("ui.escape.handled", branch="ignored", busy=app._busy)
    return False


def on_prompt_composer_changed(app: Any) -> None:
    current_text = app._current_prompt_text()
    if current_text and bool(getattr(app, "_shortcut_overlay_active", False)):
        app._shortcut_overlay_active = False
    if (
        app._suppressed_slash_popup_text is not None
        and current_text != app._suppressed_slash_popup_text
    ):
        app._suppressed_slash_popup_text = None
    app._retain_pending_pastes_for_text(current_text)
    app._sync_prompt_history_navigation()
    app._update_completion_popup()
    app._refresh_prompt_composer()
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return


def action_toggle_latest_web_item(app: Any) -> None:
    for entry in range(len(app._transcript_entries) - 1, -1, -1):
        candidate = app._transcript_entries[entry]
        if candidate.layer != "web" or not candidate.expanded_lines:
            continue
        candidate.expanded = not candidate.expanded
        try:
            app._sync_transcript()
        except NoMatches:
            pass
        finally:
            app._focus_input()
        return
