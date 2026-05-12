from __future__ import annotations

from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.runtime_kernels.base import KernelEngine

_HISTORY_TEXT_BLOCK_TYPES = {
    "input_text",
    "output_text",
    "reasoning",
    "summary_text",
    "text",
}


def _hydrate_codex_runtime_from_session_metadata(runtime: Any) -> None:
    metadata = dict(getattr(getattr(runtime, "kernel_session", None), "metadata", {}) or {})
    turns = metadata.get("thread_turns")
    if not isinstance(turns, list):
        return
    history_turns = _codex_turns_to_history_turns(turns)
    if history_turns:
        runtime.history_turns = history_turns
        runtime.turn_results = [
            PromptResponse(
                user_text=str(turn.get("user_text") or ""),
                assistant_text=str(turn.get("assistant_text") or ""),
                status=dict(turn.get("status") or {}),
                turn_events=[
                    dict(item)
                    for item in list(turn.get("turn_events") or [])
                    if isinstance(item, dict)
                ],
                protocol_diagnostics={
                    "runtime_kernel": "codex_sidecar",
                    "kernel_session_id": str(
                        getattr(getattr(runtime, "kernel_session", None), "session_id", "") or ""
                    ),
                    "turn_id": str(turn.get("codex_turn_id") or ""),
                    "codex_sidecar_events": list(turn.get("codex_sidecar_events") or []),
                },
            )
            for turn in history_turns
        ]
        history: list[dict[str, Any]] = []
        for turn in history_turns:
            user_text = str(turn.get("user_text") or "").strip()
            assistant_text = str(turn.get("assistant_text") or "").strip()
            if user_text:
                history.append({"type": "message", "role": "user", "content": user_text})
            if assistant_text:
                history.append({"type": "message", "role": "assistant", "content": assistant_text})
        runtime.history = history


def _restore_tab_provider(runtime: Any, tab_info: Any) -> None:
    saved_provider = str(getattr(tab_info, "provider_name", "") or "").strip()
    saved_model = str(getattr(tab_info, "provider_model", "") or "").strip()
    if not saved_provider:
        return
    try:
        agent = getattr(runtime, "agent", None)
        current_status = dict(getattr(agent, "provider_status", lambda: {})() or {})
        current_provider = str(current_status.get("provider_name") or "").strip()
        if current_provider == saved_provider:
            return
        switch_fn = getattr(agent, "switch_provider", None)
        if callable(switch_fn):
            switch_fn(saved_provider, write_scope="session")
    except Exception:
        pass
    if not saved_model:
        return
    try:
        configure_fn = getattr(runtime, "configure_model_selection", None)
        if callable(configure_fn):
            configure_fn(model=saved_model, write_scope="session")
    except Exception:
        pass


def _restore_runtime_transcript_snapshot(app: Any, runtime: Any) -> tuple[list, list]:
    saved_entries = list(getattr(app, "_transcript_entries", []) or [])
    saved_lines = list(getattr(app, "_transcript_lines", []) or [])
    saved_snapshot_entries = getattr(app, "_transcript_screen_snapshot_entries", None)
    mgr = getattr(app, "_tab_manager", None)
    active_session = getattr(mgr, "active_session", None) if mgr is not None else None
    saved_runtime = getattr(active_session, "runtime", None)
    app._transcript_entries = []
    app._transcript_lines = []
    app._transcript_screen_snapshot_entries = None
    try:
        if active_session is not None:
            active_session.runtime = runtime
        app._restore_transcript_from_runtime_history()
        return list(app._transcript_entries), list(app._transcript_lines)
    finally:
        if active_session is not None:
            active_session.runtime = saved_runtime
        app._transcript_entries = saved_entries
        app._transcript_lines = saved_lines
        app._transcript_screen_snapshot_entries = saved_snapshot_entries


def _tab_session_engine_for_runtime(runtime: Any) -> KernelEngine:
    kernel_session = getattr(runtime, "kernel_session", None)
    engine = str(getattr(kernel_session, "engine", "") or "").strip()
    if engine == "codex_sidecar":
        return "codex_sidecar"
    return "agenthub_python"


def _tab_session_kernel_session_id(runtime: Any) -> str:
    kernel_session = getattr(runtime, "kernel_session", None)
    return str(getattr(kernel_session, "session_id", "") or "").strip()


def _provider_status_for_runtime(runtime: Any) -> dict[str, str]:
    try:
        agent = getattr(runtime, "agent", None)
        status_fn = getattr(agent, "provider_status", None)
        if callable(status_fn):
            return {str(key): str(value) for key, value in dict(status_fn() or {}).items()}
    except Exception:
        pass
    return {}


def _merge_status_preserving_known_values(
    base: dict[str, Any],
    update: dict[str, Any],
) -> dict[str, str]:
    merged = {str(key): str(value) for key, value in dict(base or {}).items() if value is not None}
    for key, value in dict(update or {}).items():
        text = str(value or "").strip()
        if not text or text == "-":
            continue
        merged[str(key)] = text
    return merged


def _without_pending_approval_status(status: dict[str, Any]) -> dict[str, str]:
    result = {
        str(key): str(value) for key, value in dict(status or {}).items() if value is not None
    }
    result["pending_approvals"] = "0"
    result["latest_pending_approval_id"] = "-"
    return result


def _initial_status_data_for_runtime(app: Any, runtime: Any) -> dict[str, str]:
    try:
        from cli.agent_cli import app_runtime_support_runtime

        session_started_at = getattr(app, "session_started_at", None)
        if hasattr(session_started_at, "strftime"):
            session_started_text = session_started_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            session_started_text = str(session_started_at or "")
        return {
            str(key): str(value)
            for key, value in app_runtime_support_runtime.initial_status_data(
                runtime=runtime,
                session_started_text=session_started_text,
                thread_id=getattr(runtime, "thread_id", None),
                thread_name=getattr(runtime, "thread_name", None),
            ).items()
            if value is not None
        }
    except Exception:
        status: dict[str, str] = {}
        try:
            status.update(
                {
                    str(key): str(value)
                    for key, value in dict(
                        getattr(runtime, "runtime_policy_status", lambda: {})() or {}
                    ).items()
                    if value is not None
                }
            )
        except Exception:
            pass
        try:
            status.update(
                {
                    str(key): str(value)
                    for key, value in dict(
                        getattr(runtime, "approval_status", lambda: {})() or {}
                    ).items()
                    if value is not None
                }
            )
        except Exception:
            pass
        status.update(_provider_status_for_runtime(runtime))
        status["thread_id"] = str(getattr(runtime, "thread_id", "") or "-")
        status["thread_name"] = str(getattr(runtime, "thread_name", "") or "-")
        return status


def _initial_status_data_for_new_tab(app: Any, runtime: Any) -> dict[str, str]:
    return _without_pending_approval_status(_initial_status_data_for_runtime(app, runtime))


def _fork_status_data_for_runtime(
    source_status: dict[str, Any],
    runtime: Any,
) -> dict[str, str]:
    return _without_pending_approval_status(
        {
            str(key): str(value)
            for key, value in {
                **dict(source_status or {}),
                **_provider_status_for_runtime(runtime),
            }.items()
            if value is not None
        }
    )


def _history_content_value_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for block in value:
            text = _history_content_value_text(block)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        block_type = str(value.get("type") or value.get("item_type") or "").strip().lower()
        if block_type and block_type not in _HISTORY_TEXT_BLOCK_TYPES:
            return ""
        for key in ("text", "output_text", "stdout", "stderr", "summary_text", "message", "error"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return ""


def _history_item_content_text(item: dict[str, Any]) -> str:
    for key in ("content", "summary", "text", "output"):
        if key not in item:
            continue
        text = _history_content_value_text(item.get(key))
        if text:
            return text
    return ""


def _fork_runtime_transcript_source_items(runtime: Any) -> list[dict[str, Any]]:
    planner_items = [
        dict(item)
        for item in list(getattr(runtime, "_planner_input_items", []) or [])
        if isinstance(item, dict)
    ]
    if planner_items:
        return planner_items
    return [
        dict(item) for item in list(getattr(runtime, "history", []) or []) if isinstance(item, dict)
    ]


def _history_item_to_transcript_entry(item: dict[str, Any]) -> Any | None:
    from cli.agent_cli.ui.transcript_history import (
        assistant_message_entry,
        reasoning_message_entry,
        system_notice_entry,
        user_message_entry,
    )

    item_type = str(item.get("type") or item.get("item_type") or "").strip().lower()
    role = str(item.get("role") or "").strip().lower()
    if item_type == "message" or role in ("user", "assistant"):
        text = _history_item_content_text(item)
        if not text:
            return None
        if role == "user":
            return user_message_entry(text)
        if role == "assistant":
            return assistant_message_entry(text)
        return None
    if item_type == "reasoning":
        text = _history_item_content_text(item)
        if not text:
            return None
        return reasoning_message_entry(text)
    if item_type == "function_call":
        name = str(item.get("name") or "")
        if not name:
            return None
        return system_notice_entry(f"⚙ {name}")
    if item_type == "function_call_output":
        call_id = str(item.get("call_id") or "").strip()
        text = _history_item_content_text(item)
        if text:
            label = f"⚙ {call_id} output" if call_id else "⚙ tool output"
            return system_notice_entry(f"{label}: {' '.join(text.split())}")
        if call_id:
            return system_notice_entry(f"⚙ {call_id} output")
    return None


def _codex_turns_to_history_turns(turns: list[Any]) -> list[dict[str, Any]]:
    history_turns: list[dict[str, Any]] = []
    for raw_turn in list(turns or []):
        if not isinstance(raw_turn, dict):
            continue
        user_parts: list[str] = []
        assistant_parts: list[str] = []
        for raw_item in list(raw_turn.get("items") or []):
            if not isinstance(raw_item, dict):
                continue
            item_type = str(raw_item.get("type") or raw_item.get("item_type") or "").strip()
            if item_type == "userMessage":
                text = _history_item_content_text(
                    {
                        "type": "message",
                        "role": "user",
                        "content": raw_item.get("content") or raw_item.get("text") or "",
                    }
                )
                if text:
                    user_parts.append(text)
            elif item_type == "agentMessage":
                text = str(raw_item.get("text") or "").strip()
                if text:
                    assistant_parts.append(text)
        user_text = "\n\n".join(user_parts).strip()
        assistant_text = "\n\n".join(assistant_parts).strip()
        if user_text or assistant_text:
            history_turns.append(
                {
                    "user_text": user_text,
                    "assistant_text": assistant_text,
                    "turn_events": [
                        dict(item)
                        for item in list(raw_turn.get("turn_events") or [])
                        if isinstance(item, dict)
                    ],
                    "codex_sidecar_events": [
                        dict(item)
                        for item in list(raw_turn.get("codex_sidecar_events") or [])
                        if isinstance(item, dict)
                    ],
                    "status": (
                        dict(raw_turn.get("status"))
                        if isinstance(raw_turn.get("status"), dict)
                        else {}
                    ),
                    "codex_turn_id": str(raw_turn.get("id") or ""),
                }
            )
    return history_turns
