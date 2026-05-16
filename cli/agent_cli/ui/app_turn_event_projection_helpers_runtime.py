from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.runtime_core import activity_events_for_tool_event
from cli.agent_cli.ui import TranscriptEntry, transcript_formatting_helpers_runtime
from cli.agent_cli.ui.transcript_formatting import format_patch_activity_lines
from cli.agent_cli.ui.transcript_structured_runtime import (
    activity_payload,
    message_payload,
    reasoning_payload,
)


def _is_delegated_agent_item(event: dict[str, object], item: dict[str, object]) -> bool:
    return isinstance(event.get("delegated_agent"), dict) or isinstance(
        item.get("delegated_agent"), dict
    )


def turn_event_activity(
    app: Any,
    event: dict[str, object],
    *,
    observable_turn_item_fn: Callable[[Any, dict[str, object]], dict[str, object]],
    command_execution_exploration_activity_fn: Callable[..., ActivityEvent | None],
    command_activity_params_fn: Callable[[dict[str, object]], dict[str, object]],
    command_display_text_from_mapping_fn: Callable[..., str],
    turn_event_command_text_fn: Callable[[dict[str, object]], str],
    turn_event_command_detail_fn: Callable[[dict[str, object]], str],
    turn_event_running_tool_detail_fn: Callable[[dict[str, object]], str],
    native_web_search_activity_fn: Callable[[str | None, dict[str, object]], ActivityEvent | None],
    expert_review_activity_fn: Callable[[str | None, dict[str, object]], ActivityEvent | None],
    tool_event_from_turn_tool_item_fn: Callable[[dict[str, object]], Any],
) -> ActivityEvent | None:
    event_type = str(event.get("type") or "").strip()
    if event_type not in {"item.started", "item.updated", "item.completed"}:
        return None
    item = event.get("item")
    if not isinstance(item, dict):
        return None
    item = observable_turn_item_fn(app, item)
    item_type = str(item.get("type") or "").strip()
    if item_type == "command_execution":
        exploration_activity = command_execution_exploration_activity_fn(
            item, event_type=event_type
        )
        if exploration_activity is not None:
            return exploration_activity
        command_params = command_activity_params_fn(item)
        command_text = command_display_text_from_mapping_fn(
            command_params, single_line=True
        ) or turn_event_command_text_fn(item)
        status_text = str(item.get("status") or "").strip().lower()
        if event_type in {"item.started", "item.updated"} or status_text == "in_progress":
            return ActivityEvent(
                title=f"Running {command_text}",
                status="running",
                detail="",
                kind="command",
                code="command.run",
                params=command_params,
            )
        exit_code = item.get("exit_code")
        ok = exit_code in {0, "0", None} and status_text != "failed"
        completed_params = dict(command_params)
        completed_params["exit_code"] = exit_code
        return ActivityEvent(
            title=f"Ran {command_text}" if ok else f"Command failed: {command_text}",
            status="success" if ok else "error",
            detail=turn_event_command_detail_fn(item),
            kind="command",
            code="command.run",
            params=completed_params,
        )
    if item_type == "web_search_call":
        return native_web_search_activity_fn(event_type, item)
    if item_type == "expert_review":
        return expert_review_activity_fn(event_type, item)
    if item_type != "mcp_tool_call":
        return None
    if event_type in {"item.started", "item.updated"}:
        tool_name = str(item.get("tool") or "").strip()
        if not tool_name:
            return None
        if tool_name == "web_search":
            arguments = item.get("arguments")
            query_text = ""
            if isinstance(arguments, dict):
                query_text = str(arguments.get("query") or "").strip()
            return ActivityEvent(
                title="Searching the web",
                status="running",
                detail=f"query={query_text}" if query_text else "",
                kind="web",
                code="web.search",
                params={
                    "tool_name": tool_name,
                    "query": query_text,
                    "web_search_outcome": str(item.get("search_phase") or "").strip(),
                },
            )
        return ActivityEvent(
            title=f"Running {tool_name}",
            status="running",
            detail=turn_event_running_tool_detail_fn(item),
            kind="tool",
            code="tool.run",
            params={"tool_name": tool_name},
        )
    tool_event = tool_event_from_turn_tool_item_fn(item)
    if tool_event is None:
        return None
    activity_events = activity_events_for_tool_event(tool_event)
    return activity_events[0] if activity_events else None


def turn_event_entry(
    app: Any,
    event: dict[str, object],
    *,
    activity: ActivityEvent | None = None,
    observable_turn_item_fn: Callable[[Any, dict[str, object]], dict[str, object]],
    reference_visible_reasoning_text_fn: Callable[[str], str],
    command_execution_exploration_entry_fn: Callable[..., TranscriptEntry | None],
    command_execution_entry_fn: Callable[..., TranscriptEntry],
    todo_list_entry_fn: Callable[..., TranscriptEntry],
    activity_entry_fn: Callable[[ActivityEvent | None], TranscriptEntry | None],
    tool_event_from_turn_tool_item_fn: Callable[[dict[str, object]], Any],
    local_exec_like_mcp_tool_entry_fn: Callable[..., TranscriptEntry | None],
    view_image_mcp_tool_entry_fn: Callable[..., TranscriptEntry | None],
    view_document_mcp_tool_entry_fn: Callable[..., TranscriptEntry | None],
    is_exploration_mcp_tool_fn: Callable[[dict[str, object]], bool],
    mcp_tool_call_entry_fn: Callable[..., TranscriptEntry],
    input_image_output_entry_fn: Callable[..., TranscriptEntry | None],
    document_output_entry_fn: Callable[..., TranscriptEntry | None],
) -> TranscriptEntry | None:
    event_type = str(event.get("type") or "").strip()
    if event_type not in {"item.started", "item.updated", "item.completed"}:
        return None
    item = event.get("item")
    if not isinstance(item, dict):
        return None
    item = observable_turn_item_fn(app, item)
    item_type = str(item.get("type") or "").strip()
    item_key = app._turn_event_item_key(item)
    if item_type == "reasoning":
        if event_type not in {"item.updated", "item.completed"}:
            return None
        text = reference_visible_reasoning_text_fn(str(item.get("text") or ""))
        if not text:
            return None
        return TranscriptEntry(
            kind="reasoning",
            layer="reasoning",
            lines=app._format_transcript_block(text, first_prefix="• ", continuation_prefix="  "),
            status="reasoning",
            activity_key=app._scope_activity_key(item_key),
            raw_content=text,
            structured=reasoning_payload(text),
            render_mode="reasoning_markdown",
        )
    if item_type == "command_execution":
        exploration_entry = command_execution_exploration_entry_fn(
            item,
            item_key=app._scope_activity_key(item_key),
            event_type=event_type,
        )
        if exploration_entry is not None:
            return exploration_entry
        return command_execution_entry_fn(app, item, item_key=item_key)
    if item_type == "todo_list":
        return todo_list_entry_fn(app, item, item_key=item_key)
    if item_type == "expert_review":
        activity_entry_value = activity_entry_fn(activity) if activity is not None else None
        if activity_entry_value is None:
            return None
        return replace(activity_entry_value, activity_key=app._scope_activity_key(item_key))
    if item_type == "mcp_tool_call":
        tool_event = tool_event_from_turn_tool_item_fn(item)
        if tool_event is not None and tool_event.name in {
            "patch_approval_requested",
            "shell_approval_requested",
            "background_teammate_approval_requested",
            "approval_list",
            "approval_decision",
        }:
            activity_events = activity_events_for_tool_event(tool_event)
            if activity_events:
                approval_activity = activity_events[0]
                approval_entry = activity_entry_fn(approval_activity)
                if approval_entry is not None:
                    return replace(approval_entry, activity_key=app._scope_activity_key(item_key))
                approval_lines = format_patch_activity_lines(approval_activity)
                if approval_lines:
                    return TranscriptEntry(
                        kind="activity",
                        layer="tool",
                        lines=approval_lines,
                        status=approval_activity.status,
                        activity_key=app._scope_activity_key(item_key),
                        structured=activity_payload(approval_activity),
                        render_mode="tool_approval",
                    )
        special_entry = local_exec_like_mcp_tool_entry_fn(app, item, item_key=item_key)
        if special_entry is not None:
            return special_entry
        image_ready_entry = view_image_mcp_tool_entry_fn(app, item, item_key=item_key)
        if image_ready_entry is not None:
            return image_ready_entry
        document_ready_entry = view_document_mcp_tool_entry_fn(app, item, item_key=item_key)
        if document_ready_entry is not None:
            return document_ready_entry
        if str(item.get("tool") or "").strip() == "web_search":
            web_entry = activity_entry_fn(activity) if activity is not None else None
            if web_entry is not None:
                return replace(web_entry, activity_key=app._scope_activity_key(item_key))
        if not is_exploration_mcp_tool_fn(item):
            return mcp_tool_call_entry_fn(app, item, item_key=item_key)
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        image_injected_entry = input_image_output_entry_fn(app, item, item_key=item_key)
        if image_injected_entry is not None:
            return image_injected_entry
        document_projected_entry = document_output_entry_fn(app, item, item_key=item_key)
        if document_projected_entry is not None:
            return document_projected_entry
    if item_type == "agent_message":
        if event_type not in {"item.updated", "item.completed"}:
            return None
        # Claude Code streams subagent messages under parent_tool_use_id and does not
        # render the child final assistant text as a top-level transcript answer.
        if _is_delegated_agent_item(event, item):
            return None
        text = str(item.get("text") or "").strip()
        if not text:
            return None
        if transcript_formatting_helpers_runtime.is_approval_request_fallback_text(text):
            return None
        if app._is_interrupt_terminal_message(text):
            item_key = app._interrupt_terminal_activity_key()
        status = app._assistant_message_status(text)
        text = app._localized_assistant_text(text)
        phase = app._agent_message_phase(item)
        layer = "commentary" if phase == "commentary" else "final"
        return TranscriptEntry(
            kind="turn_item",
            layer=layer,
            lines=app._format_transcript_block(text, first_prefix="• ", continuation_prefix="  "),
            status="error" if status == "error" else phase,
            activity_key=app._scope_activity_key(item_key),
            raw_content=text,
            structured=message_payload(
                name="agent_message",
                text=text,
                state="error" if status == "error" else "completed",
                metadata={"phase": phase},
            ),
            render_mode="markdown",
        )
    if activity is None:
        return None
    entry = activity_entry_fn(activity)
    if entry is None:
        return None
    return TranscriptEntry(
        kind=entry.kind,
        layer=entry.layer,
        lines=list(entry.lines),
        status=entry.status,
        activity_key=app._scope_activity_key(item_key or entry.activity_key),
        exploration_details=list(entry.exploration_details) if entry.exploration_details else None,
        expanded_lines=list(entry.expanded_lines) if entry.expanded_lines else None,
        expanded=entry.expanded,
        raw_content=entry.raw_content,
        structured=(
            dict(entry.structured) if isinstance(entry.structured, dict) else entry.structured
        ),
        render_mode=entry.render_mode,
        search_text=entry.search_text,
    )
