from __future__ import annotations

import json
from typing import Any, Callable

from cli.agent_cli.command_execution_summary_runtime import command_execution_summaries_from_mapping
from cli.agent_cli.models import (
    ActivityEvent,
    REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
    activity_code,
    is_user_interrupt_assistant_text,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry


def agent_message_phase(item: dict[str, object]) -> str:
    phase = str(item.get("phase") or "").strip().lower()
    return phase or "final_answer"


def final_separator_label(
    *,
    t_fn: Callable[..., str],
    completion_time: str,
    elapsed: str,
) -> str:
    return t_fn(
        "transcript.completion_separator",
        time=str(completion_time or "").strip(),
        elapsed=str(elapsed or "").strip(),
    )


def should_insert_final_separator(
    *,
    entry: TranscriptEntry,
    transcript_entries: list[TranscriptEntry],
    live_turn_had_work_activity: bool,
    live_turn_final_separator_emitted: bool,
) -> bool:
    if entry.kind == "separator" or entry.layer != "final":
        return False
    if not live_turn_had_work_activity or live_turn_final_separator_emitted:
        return False
    for candidate in reversed(transcript_entries):
        if candidate.kind == "blank":
            continue
        return candidate.kind != "separator"
    return False


def is_interrupt_terminal_message(text: str) -> bool:
    return is_user_interrupt_assistant_text(text) or str(text or "").strip() == REFERENCE_CONVERSATION_INTERRUPTED_TEXT


def should_suppress_turn_event_after_interrupt(
    event: dict[str, object],
    *,
    live_turn_interrupt_requested: bool,
    is_interrupt_terminal_message_fn: Callable[[str], bool],
) -> bool:
    if not live_turn_interrupt_requested:
        return False
    event_type = str(event.get("type") or "").strip()
    if event_type in {"turn.completed", "turn.failed"}:
        return False
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    item_type = str(item.get("type") or "").strip()
    if item_type == "agent_message":
        return not is_interrupt_terminal_message_fn(str(item.get("text") or ""))
    return item_type in {"reasoning", "command_execution", "mcp_tool_call", "todo_list", "expert_review"}


def should_suppress_live_activity_event(
    event: ActivityEvent,
    *,
    live_turn_interrupt_requested: bool,
    live_turn_event_sequence: int,
) -> bool:
    if live_turn_interrupt_requested:
        return True
    if live_turn_event_sequence <= 0:
        return False
    if event.status == "error":
        return False
    code = activity_code(event)
    discriminator = code or str(event.title or "").strip()
    if not discriminator:
        return False
    if code == "command.run" or event.kind == "command":
        return True
    if event.kind != "tool":
        return False
    return code in {"dir.list", "file.list", "file.search", "dir.search", "file.read", "tool.run"}


def turn_event_signature(event: dict[str, object], *, backfill_signature_fn: Callable[[dict[str, object]], str]) -> str:
    item = event.get("item")
    if isinstance(item, dict) and str(item.get("type") or "").strip() == "reasoning":
        return backfill_signature_fn(event)
    try:
        return json.dumps(event, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(event)


def normalized_turn_event_value(value: object) -> object:
    if isinstance(value, dict):
        item_type = str(value.get("type") or "").strip()
        if item_type == "agent_message":
            normalized_agent_message: dict[str, object] = {}
            for key, item in dict(value).items():
                if str(key) == "id":
                    continue
                normalized_agent_message[str(key)] = normalized_turn_event_value(item)
            phase = str(normalized_agent_message.get("phase") or "").strip().lower()
            normalized_agent_message["phase"] = phase or "final_answer"
            return normalized_agent_message
        if str(value.get("type") or "").strip() == "reasoning":
            normalized_reasoning: dict[str, object] = {}
            for key, item in dict(value).items():
                if str(key) in {"id", "provider_item_id", "status", "summary", "encrypted_content"}:
                    continue
                normalized_reasoning[str(key)] = normalized_turn_event_value(item)
            return normalized_reasoning
        normalized: dict[str, object] = {}
        for key, item in dict(value).items():
            if str(key) == "id":
                continue
            normalized[str(key)] = normalized_turn_event_value(item)
        return normalized
    if isinstance(value, list):
        return [normalized_turn_event_value(item) for item in list(value)]
    return value


def turn_event_backfill_signature(event: dict[str, object]) -> str:
    normalized = normalized_turn_event_value(dict(event or {}))
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(normalized)


def turn_event_item_key(item: dict[str, object]) -> str | None:
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        return None
    return f"turn_item:{item_id}"


def extract_first_bold(text: str) -> str | None:
    content = str(text or "")
    start = content.find("**")
    if start < 0:
        return None
    end = content.find("**", start + 2)
    if end < 0:
        return None
    inner = content[start + 2 : end].strip()
    return inner or None


def reasoning_summary_text(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    start = content.find("**")
    if start < 0:
        return ""
    end = content.find("**", start + 2)
    if end < 0:
        return ""
    return content[end + 2 :].strip()


def _activity_param_text(event: ActivityEvent, *keys: str) -> str:
    params = event.params or {}
    for key in keys:
        value = params.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _search_subject(query: str, path: str) -> str:
    if query and path:
        return f"{query} in {path}"
    return query or path


def _command_running_label(event: ActivityEvent) -> str:
    summaries = command_execution_summaries_from_mapping(dict(event.params or {}))
    if not summaries:
        return ""
    primary = summaries[0]
    if primary.kind == "read":
        subject = str(primary.name or primary.path or "").strip()
        return f"Reading {subject}" if subject else "Reading file"
    if primary.kind == "list":
        subject = str(primary.path or ".").strip() or "."
        return f"Listing {subject}"
    if primary.kind == "search":
        subject = _search_subject(
            str(primary.query or "").strip(),
            str(primary.path or "").strip(),
        )
        return f"Searching {subject}" if subject else "Searching files"
    return ""


def running_activity_label(
    event: ActivityEvent,
    *,
    format_activity_summary_fn: Callable[[ActivityEvent], str],
) -> str:
    if event.status == "error":
        return ""
    code = activity_code(event)
    if code == "file.read":
        subject = _activity_param_text(event, "file_path", "path")
        return f"Reading {subject}" if subject else "Reading file"
    if code in {"dir.list", "file.list"}:
        subject = _activity_param_text(event, "dir_path", "path") or "."
        return f"Listing {subject}"
    if code in {"dir.search", "file.search"}:
        query = _activity_param_text(event, "query", "pattern")
        path = _activity_param_text(event, "path")
        subject = _search_subject(query, path)
        return f"Searching {subject}" if subject else "Searching files"
    if code == "command.run" or event.kind == "command":
        label = _command_running_label(event)
        if label:
            return label
    summary = format_activity_summary_fn(event).strip()
    if summary.startswith("• "):
        summary = summary[2:].strip()
    return summary
