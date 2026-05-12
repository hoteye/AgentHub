from __future__ import annotations

import threading
from typing import Any

from cli.agent_cli import (
    app_runtime_flow_normalization_helpers_runtime as normalization_helpers_runtime,
)
from cli.agent_cli import app_runtime_flow_projection_helpers_runtime as projection_helpers_runtime
from cli.agent_cli import app_runtime_flow_pure_helpers_runtime as pure_helpers_runtime
from cli.agent_cli.app_runtime_flow_request_user_input_helpers import (
    _normalize_request_user_input_questions,
    _normalize_request_user_input_response,
    _PendingRequestUserInput,
)


def _active_tab_id(app: Any) -> str:
    mgr = getattr(app, "_tab_manager", None)
    active_tab_id = str(getattr(mgr, "active_tab_id", "") or "").strip()
    return active_tab_id or "main"


def _pending_tab_session(app: Any, pending: _PendingRequestUserInput) -> Any | None:
    mgr = getattr(app, "_tab_manager", None)
    if mgr is None:
        return None
    getter = getattr(mgr, "get", None)
    if not callable(getter):
        return None
    return getter(str(getattr(pending, "tab_id", "") or "").strip() or _active_tab_id(app))


def _set_session_pending_request_user_input(
    app: Any,
    pending: _PendingRequestUserInput,
) -> bool:
    session = _pending_tab_session(app, pending)
    if session is None:
        return True
    existing = getattr(session, "pending_request_user_input", None)
    if existing is not None and existing is not pending:
        return False
    session.pending_request_user_input = pending
    return True


def _clear_session_pending_request_user_input(
    app: Any,
    pending: _PendingRequestUserInput,
) -> None:
    session = _pending_tab_session(app, pending)
    if session is not None and getattr(session, "pending_request_user_input", None) is pending:
        session.pending_request_user_input = None


def install_local_request_user_input_handler(app: Any) -> None:
    previous = getattr(app.runtime, "request_user_input_handler", None)
    app._request_user_input_previous_handler = previous
    tab_id = _active_tab_id(app)
    app.runtime.request_user_input_handler = (
        lambda payload, _tid=tab_id: app._handle_request_user_input_from_runtime_for_tab(
            _tid, payload
        )
    )


def restore_request_user_input_handler(app: Any) -> None:
    previous = app._request_user_input_previous_handler
    if previous is None:
        app.runtime.request_user_input_handler = None
    else:
        app.runtime.request_user_input_handler = previous
    app._request_user_input_previous_handler = None


def handle_request_user_input_from_runtime(
    app: Any,
    payload: dict[str, Any],
    *,
    tab_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_questions = _normalize_request_user_input_questions(
        (payload or {}).get("questions"),
    )
    pending_projection = projection_helpers_runtime.build_request_user_input_pending(
        normalized_questions,
    )
    pending = _PendingRequestUserInput(
        payload=pending_projection.payload,
        question_ids=pending_projection.question_ids,
        tab_id=str(tab_id or _active_tab_id(app)).strip() or _active_tab_id(app),
    )
    with app._request_user_input_pending_lock:
        if not _set_session_pending_request_user_input(app, pending):
            return None
        if pending.tab_id == _active_tab_id(app):
            if app._request_user_input_pending is not None:
                _clear_session_pending_request_user_input(app, pending)
                return None
            app._request_user_input_pending = pending
    if pending.tab_id == _active_tab_id(app):
        if getattr(app, "_thread_id", None) == threading.get_ident():
            app._dispatch_request_user_input_prompt(pending)
        else:
            app.call_from_thread(app._dispatch_request_user_input_prompt, pending)
    else:
        refresh_indicators = getattr(app, "_refresh_tab_pending_interaction_indicators", None)
        if callable(refresh_indicators):
            if getattr(app, "_thread_id", None) == threading.get_ident():
                refresh_indicators()
            else:
                app.call_from_thread(refresh_indicators)
        else:
            refresh_top_title = getattr(app, "_refresh_top_title_bar", None)
            if callable(refresh_top_title):
                if getattr(app, "_thread_id", None) == threading.get_ident():
                    refresh_top_title()
                else:
                    app.call_from_thread(refresh_top_title)
    pending.response_event.wait()
    with app._request_user_input_pending_lock:
        if app._request_user_input_pending is pending:
            app._request_user_input_pending = None
        _clear_session_pending_request_user_input(app, pending)
    if pending.cancelled or not isinstance(pending.response_payload, dict):
        return None
    return dict(pending.response_payload)


def dispatch_request_user_input_prompt(app: Any, pending: _PendingRequestUserInput) -> None:
    questions = [
        dict(item)
        for item in list((pending.payload or {}).get("questions") or [])
        if isinstance(item, dict)
    ]
    if pending.tab_id != _active_tab_id(app):
        return
    with app._request_user_input_pending_lock:
        if app._request_user_input_pending is None:
            app._request_user_input_pending = pending
    app._set_request_user_input_waiting(True)
    if not pending.prompt_dispatched:
        pending.prompt_dispatched = True
        notice = projection_helpers_runtime.request_user_input_requested_notice(len(questions))
        app._write_system_notice(
            app._request_user_input_notice_text(
                key=notice.key,
                legacy_en=notice.legacy_en,
                **notice.kwargs,
            )
        )
    if app._present_request_user_input_modal(pending.payload):
        return
    responder = app._request_user_input_test_responder
    if callable(responder):
        response: dict[str, Any] | None = None
        try:
            maybe_response = responder(
                projection_helpers_runtime.request_user_input_modal_payload(pending.payload)
            )
            if isinstance(maybe_response, dict):
                response = _normalize_request_user_input_response(
                    maybe_response,
                    question_ids=pending.question_ids,
                )
        except Exception:
            response = None
        if response is not None:
            app._on_request_user_input_submit(response)
            return
    notice = projection_helpers_runtime.request_user_input_interactive_unavailable_notice()
    app._write_system_notice(
        app._request_user_input_notice_text(
            key=notice.key,
            legacy_en=notice.legacy_en,
            **notice.kwargs,
        )
    )
    app._on_request_user_input_cancel()


def present_request_user_input_modal(app: Any, payload: dict[str, Any]) -> bool:
    presenter = app._request_user_input_modal_presenter
    if callable(presenter):
        try:
            accepted = bool(
                presenter(
                    payload=projection_helpers_runtime.request_user_input_modal_payload(payload),
                    on_submit=app._on_request_user_input_submit,
                    on_cancel=app._on_request_user_input_cancel,
                )
            )
        except Exception:
            accepted = False
        if accepted:
            return True
    try:
        from cli.agent_cli.ui.request_user_input_modal import present_request_user_input
    except Exception:
        return False
    if not callable(present_request_user_input):
        return False
    try:
        return bool(
            present_request_user_input(
                app=app,
                payload=projection_helpers_runtime.request_user_input_modal_payload(payload),
                on_submit=app._on_request_user_input_submit,
                on_cancel=app._on_request_user_input_cancel,
            )
        )
    except Exception:
        return False


def cancel_request_user_input_on_escape(app: Any) -> bool:
    with app._request_user_input_pending_lock:
        pending = app._request_user_input_pending
    if pending is None:
        return False
    notice = projection_helpers_runtime.request_user_input_user_cancelled_notice()
    app._write_system_notice(
        app._request_user_input_notice_text(
            key=notice.key,
            legacy_en=notice.legacy_en,
            **notice.kwargs,
        )
    )
    app._resolve_pending_request_user_input(response=None, cancelled=True)
    return True


def cancel_pending_request_user_input(app: Any, reason: str) -> None:
    with app._request_user_input_pending_lock:
        pending = app._request_user_input_pending
        tab_pending = []
        mgr = getattr(app, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        if isinstance(tabs, dict):
            for session in tabs.values():
                candidate = getattr(session, "pending_request_user_input", None)
                if candidate is not None and candidate is not pending:
                    tab_pending.append(candidate)
    if pending is None and not tab_pending:
        return
    if pending is not None:
        notice = projection_helpers_runtime.request_user_input_cancelled_reason_notice(
            app._request_user_input_cancel_reason_label(reason),
        )
        app._write_system_notice(
            app._request_user_input_notice_text(
                key=notice.key,
                legacy_en=notice.legacy_en,
                **notice.kwargs,
            )
        )
        app._resolve_pending_request_user_input(response=None, cancelled=True)
    for candidate in tab_pending:
        candidate.cancelled = True
        candidate.response_payload = None
        _clear_session_pending_request_user_input(app, candidate)
        candidate.response_event.set()
    refresh_top_title = getattr(app, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()
    refresh_indicators = getattr(app, "_refresh_tab_pending_interaction_indicators", None)
    if callable(refresh_indicators):
        refresh_indicators()


def request_user_input_cancel_reason_label(app: Any, reason: str) -> str:
    normalized = normalization_helpers_runtime.normalize_request_user_input_cancel_reason(reason)
    if app._presentation_cli_language is None:
        if normalized == "shutdown":
            return "shutdown"
        if normalized == "escape":
            return "escape"
        return str(reason or "").strip() or "unknown"
    reason_key = pure_helpers_runtime.request_user_input_cancel_reason_key(normalized)
    if reason_key is not None:
        return app._t(reason_key)
    reason_text = str(reason or "").strip()
    if reason_text:
        return reason_text
    return app._t("system.request_user_input.reason.unknown")


def on_request_user_input_submit(app: Any, response: dict[str, Any]) -> None:
    with app._request_user_input_pending_lock:
        pending = app._request_user_input_pending
    if pending is None:
        return
    normalized_response = _normalize_request_user_input_response(
        response,
        question_ids=pending.question_ids,
    )
    resolve_pending_request_user_input(app, response=normalized_response, cancelled=False)


def on_request_user_input_cancel(app: Any) -> None:
    resolve_pending_request_user_input(app, response=None, cancelled=True)


def resolve_pending_request_user_input(
    app: Any,
    *,
    response: dict[str, Any] | None,
    cancelled: bool,
) -> None:
    with app._request_user_input_pending_lock:
        pending = app._request_user_input_pending
        if pending is None:
            return
        pending.cancelled = bool(cancelled)
        pending.response_payload = dict(response or {}) if isinstance(response, dict) else None
        app._request_user_input_pending = None
        _clear_session_pending_request_user_input(app, pending)
    app._set_request_user_input_waiting(False)
    pending.response_event.set()
    app._focus_input()
    refresh_top_title = getattr(app, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()


__all__ = [
    "cancel_pending_request_user_input",
    "cancel_request_user_input_on_escape",
    "dispatch_request_user_input_prompt",
    "handle_request_user_input_from_runtime",
    "install_local_request_user_input_handler",
    "on_request_user_input_cancel",
    "on_request_user_input_submit",
    "present_request_user_input_modal",
    "request_user_input_cancel_reason_label",
    "resolve_pending_request_user_input",
    "restore_request_user_input_handler",
]
