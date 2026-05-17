from __future__ import annotations

import os
from typing import Any

from cli.agent_cli import (
    app_runtime_flow_normalization_helpers_runtime as normalization_helpers_runtime,
)
from cli.agent_cli import app_runtime_flow_projection_helpers_runtime as projection_helpers_runtime
from cli.agent_cli import app_runtime_flow_pure_helpers_runtime as pure_helpers_runtime
from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.slash_parser import parse_slash_invocation
from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui import (
    enqueue_runtime_request as ui_enqueue_runtime_request,
)
from cli.agent_cli.ui import (
    request_worker_loop as ui_request_worker_loop,
)
from cli.agent_cli.ui import (
    transcript_preview_pane,
)
from cli.agent_cli.ui import (
    wait_for_runtime_idle as ui_wait_for_runtime_idle,
)


def on_runtime_request_start(app: Any, text: str) -> None:
    normalized = normalization_helpers_runtime.normalize_runtime_request_text(text)
    app._active_runtime_request_text = normalized
    app._active_runtime_request_is_slash = pure_helpers_runtime.is_slash_command_text(normalized)
    app._set_top_title_from_prompt(normalized)


async def enqueue_runtime_request(
    app: Any,
    text: str,
    attachments: list[PromptAttachment],
    *,
    display_text: str | None = None,
    display_attachments: list[PromptAttachment] | None = None,
    priority: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    normalized_text = str(text or "").strip()
    if app._approval_command_targets_inactive_tab(normalized_text):
        return
    if not pure_helpers_runtime.is_slash_command_text(normalized_text):
        app._queued_run_labels.append(normalized_text)
    await ui_enqueue_runtime_request(
        app._request_queue,
        text,
        attachments,
        display_text=display_text,
        display_attachments=display_attachments,
        priority=priority,
        metadata=metadata,
    )


def approval_command_targets_inactive_tab(app: Any, text: str) -> bool:
    normalized_text = str(text or "").strip()
    if not pure_helpers_runtime.is_slash_command_text(normalized_text):
        return False
    try:
        invocation = parse_slash_invocation(normalized_text, source="tui")
    except ValueError:
        return False
    if invocation.command_name not in {"approve", "reject"}:
        return False
    approval_id = next(
        (
            str(item or "").strip()
            for item in tuple(getattr(invocation, "positionals", ()) or ())
            if str(item or "").strip()
        ),
        "",
    )
    if not approval_id:
        return False
    owner_lookup = getattr(app, "_tab_id_for_pending_approval", None)
    if not callable(owner_lookup):
        return False
    owner_tab_id = str(owner_lookup(approval_id) or "").strip()
    if not owner_tab_id:
        return False
    active_tab_id = str(
        getattr(getattr(app, "_tab_manager", None), "active_tab_id", "") or ""
    ).strip()
    if not active_tab_id or owner_tab_id == active_tab_id:
        return False
    try:
        app._write_system_notice(
            app._t(
                "system.approval_wrong_tab",
                approval_id=approval_id,
                tab_id=owner_tab_id,
            )
        )
    except Exception:
        pass
    try:
        app._refresh_tab_pending_interaction_indicators()
    except Exception:
        pass
    try:
        app._focus_input()
    except Exception:
        pass
    return True


async def request_worker_loop(app: Any) -> None:
    await ui_request_worker_loop(
        queue=app._request_queue,
        runtime=app.runtime,
        set_busy=app._set_busy,
        on_request_start=app._on_runtime_request_start,
        on_request_echo=app._write_user_prompt,
        begin_activity_capture=app._begin_activity_capture,
        render_response=app._render_response,
        handle_response=app._handle_runtime_response,
        write_assistant_reply=app._write_assistant_reply,
        on_idle=app._focus_input,
    )


async def wait_for_runtime_idle(app: Any) -> None:
    await ui_wait_for_runtime_idle(app._request_queue)


def handle_runtime_response(app: Any, response: object) -> None:
    payload = app._exit_request_payload(response)
    if payload is not None:
        startup_log("app.handle_runtime_response.exit_request")
        exit_projection = projection_helpers_runtime.exit_request_projection(payload)
        app._exit_requested = True
        app._exit_thread_id = exit_projection.thread_id
        app._exit_resume_command = exit_projection.resume_command
        app._exit_summary_requires_post_run_print = True
        app.call_after_refresh(app._exit_after_command)
        return
    if pure_helpers_runtime.close_tab_request_payload(response) is not None:
        tab_count = len(getattr(getattr(app, "_tab_manager", None), "_tabs", {}) or {})
        startup_log(f"app.handle_runtime_response.close_tab_request tabs={tab_count}")
        if app._tab_manager is not None and len(app._tab_manager._tabs) > 1:
            app.call_after_refresh(app.action_close_tab)
        else:
            app.call_after_refresh(app._exit_after_command)
        return
    preview_payload = pure_helpers_runtime.preview_control_request_payload(response)
    if preview_payload is not None:
        app.call_after_refresh(
            app._handle_preview_control_request,
            str(preview_payload.get("action") or "toggle"),
        )
        return


def exit_request_payload(response: object) -> dict[str, object] | None:
    return pure_helpers_runtime.exit_request_payload(response)


def action_split_open(app: Any) -> None:
    app._handle_preview_control_request("open")
    app._refresh_split_toggle_button()


def action_split_close(app: Any) -> None:
    app._handle_preview_control_request("close")
    app._refresh_split_toggle_button()


def handle_preview_control_request(app: Any, action: str) -> None:
    normalized = str(action or "toggle").strip().lower() or "toggle"
    if normalized == "status":
        app._write_system_notice(app._preview_control_status_text())
        app._focus_input()
        return
    if normalized == "toggle":
        normalized = "open" if app._preview_pane_disabled_or_missing() else "close"
    if normalized == "close":
        transcript_preview_pane.set_preview_pane_user_disabled(True)
        closed = transcript_preview_pane.close_preview_pane()
        key = "system.preview_pane.closed" if closed else "system.preview_pane.already_closed"
        app._write_system_notice(app._t(key))
        app._focus_input()
        return
    if normalized == "open":
        transcript_preview_pane.set_preview_pane_user_disabled(False)
        pane = transcript_preview_pane.open_preview_pane()
        key = "system.preview_pane.opened" if pane else "system.preview_pane.unavailable"
        app._write_system_notice(app._t(key))
        app._focus_input()
        return
    app._write_system_notice(app._t("system.preview_pane.usage"))
    app._focus_input()


def preview_pane_disabled_or_missing() -> bool:
    if transcript_preview_pane.preview_pane_user_disabled():
        return True
    pane = str(os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if not pane:
        return True
    return not transcript_preview_pane.preview_pane_exists(pane)


def refresh_split_toggle_button(app: Any) -> None:
    try:
        from textual.widgets import Static

        btn = app.query_one("#split_toggle_btn", Static)
        is_open = not app._preview_pane_disabled_or_missing()
        compact = int(getattr(getattr(btn, "size", None), "width", 0) or 2) < 2
        if compact:
            icon = "<" if is_open else ">"
        else:
            icon = "<<" if is_open else ">>"
        btn.update(icon)
    except Exception:
        pass


def preview_control_status_text(app: Any) -> str:
    if transcript_preview_pane.preview_pane_user_disabled():
        return app._t("system.preview_pane.disabled")
    pane = str(os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if pane and transcript_preview_pane.preview_pane_exists(pane):
        return app._t("system.preview_pane.open_status", pane=pane)
    return app._t("system.preview_pane.closed_status")


__all__ = [
    "action_split_close",
    "action_split_open",
    "approval_command_targets_inactive_tab",
    "enqueue_runtime_request",
    "exit_request_payload",
    "handle_preview_control_request",
    "handle_runtime_response",
    "on_runtime_request_start",
    "preview_control_status_text",
    "preview_pane_disabled_or_missing",
    "refresh_split_toggle_button",
    "request_worker_loop",
    "wait_for_runtime_idle",
]
