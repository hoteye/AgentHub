from __future__ import annotations

_TRANSCRIPT_NAVIGATION_ACTIONS = {
    "up": "action_scroll_up",
    "down": "action_scroll_down",
    "pageup": "scroll_page_up",
    "pagedown": "scroll_page_down",
    "home": "action_scroll_home",
    "end": "action_scroll_end",
}

_REQUEST_USER_INPUT_CANCEL_REASON_KEYS = {
    "shutdown": "system.request_user_input.reason.shutdown",
    "escape": "system.request_user_input.reason.escape",
}


def is_slash_command_text(text: str) -> bool:
    return str(text or "").startswith("/")


def transcript_search_key_action(normalized_key: str, *, search_mode_active: bool) -> str | None:
    if normalized_key == "ctrl+f":
        return "activate"
    if search_mode_active:
        if normalized_key == "escape":
            return "deactivate"
        if normalized_key == "backspace":
            return "backspace"
        if normalized_key == "enter":
            return "submit"
        return None
    if normalized_key in {"n", "f3"}:
        return "next_match"
    if normalized_key in {"shift+n", "shift+f3"}:
        return "prev_match"
    return None


def transcript_search_inline_text(key: str) -> str:
    normalized = str(key or "")
    if len(normalized) != 1 or not normalized.isprintable():
        return ""
    return normalized


def transcript_search_buffer_backspace(buffer: str) -> str:
    return str(buffer or "")[:-1]


def transcript_search_buffer_append(buffer: str, value: str) -> str:
    return f"{str(buffer or '')}{str(value or '')}"


def transcript_navigation_action_name(key: str) -> str | None:
    return _TRANSCRIPT_NAVIGATION_ACTIONS.get(str(key or "").strip().lower())


def format_legacy_notice_text(legacy_en: str, **kwargs: object) -> str:
    try:
        return str(legacy_en).format(**kwargs)
    except Exception:
        return str(legacy_en)


def request_user_input_cancel_reason_key(normalized_reason: str) -> str | None:
    return _REQUEST_USER_INPUT_CANCEL_REASON_KEYS.get(str(normalized_reason or "").strip())


def exit_request_payload(response: object) -> dict[str, object] | None:
    for event in list(getattr(response, "tool_events", []) or []):
        if str(getattr(event, "name", "") or "").strip() != "app_exit_requested":
            continue
        payload = dict(getattr(event, "payload", {}) or {})
        if payload:
            return payload
    return None


def close_tab_request_payload(response: object) -> dict[str, object] | None:
    for event in list(getattr(response, "tool_events", []) or []):
        if str(getattr(event, "name", "") or "").strip() != "tab_close_requested":
            continue
        return dict(getattr(event, "payload", {}) or {})
    return None


def preview_control_request_payload(response: object) -> dict[str, object] | None:
    for event in list(getattr(response, "tool_events", []) or []):
        if str(getattr(event, "name", "") or "").strip() != "preview_control_requested":
            continue
        return dict(getattr(event, "payload", {}) or {})
    return None


__all__ = [
    "close_tab_request_payload",
    "exit_request_payload",
    "format_legacy_notice_text",
    "is_slash_command_text",
    "preview_control_request_payload",
    "request_user_input_cancel_reason_key",
    "transcript_navigation_action_name",
    "transcript_search_buffer_append",
    "transcript_search_buffer_backspace",
    "transcript_search_inline_text",
    "transcript_search_key_action",
]
