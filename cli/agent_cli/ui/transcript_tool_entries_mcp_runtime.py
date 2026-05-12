from __future__ import annotations

from typing import Callable

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.ui.transcript_formatting import format_activity_detail_lines
from cli.agent_cli.ui.transcript_history import TranscriptEntry


def local_exec_like_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    command_output_max_lines: int,
    is_local_exec_like_mcp_tool_fn,
    turn_tool_item_payload_fn,
    unwrap_shell_wrapped_command_fn,
    turn_event_result_text_fn,
    command_execution_entry_fn,
) -> TranscriptEntry | None:
    if not is_local_exec_like_mcp_tool_fn(item):
        return None
    payload = turn_tool_item_payload_fn(item)
    command_text = unwrap_shell_wrapped_command_fn(str(payload.get("command") or payload.get("cmd") or "").strip()) or "command"
    result = item.get("result")
    output_text = ""
    for key in ("stdout", "output_text", "stderr", "text"):
        value = str(payload.get(key) or "").strip()
        if value:
            output_text = value
            break
    if not output_text:
        output_text = turn_event_result_text_fn(result)
    error = item.get("error")
    if not output_text and isinstance(error, dict):
        error_text = str(error.get("message") or "").strip()
        if error_text:
            output_text = f"Error: {error_text}"
    synthetic_status = str(item.get("status") or "").strip().lower()
    if isinstance(error, dict) and str(error.get("message") or "").strip():
        synthetic_status = "failed"
    return command_execution_entry_fn(
        {
            "command": command_text,
            "aggregated_output": output_text,
            "exit_code": payload.get("returncode", payload.get("exit_code")),
            "status": synthetic_status,
        },
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        command_output_max_lines=command_output_max_lines,
    )


def mcp_tool_call_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    format_mcp_invocation_text_fn,
    turn_event_result_text_fn,
) -> TranscriptEntry:
    invocation = format_mcp_invocation_text_fn(item)
    status_text = str(item.get("status") or "").strip().lower()
    event_completed = status_text in {"completed", "failed"}
    ok = status_text == "completed" and not item.get("error")
    header = f"• {'Called' if event_completed else 'Calling'} {invocation}"
    detail = ""
    if event_completed:
        result = item.get("result")
        detail = turn_event_result_text_fn(result)
        if not detail:
            error = item.get("error")
            if isinstance(error, dict):
                error_text = str(error.get("message") or "").strip()
                if error_text:
                    detail = f"Error: {error_text}"
    lines = [header]
    if detail.strip():
        lines.extend(format_activity_detail_lines(detail))
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=lines,
        status="success" if ok else ("error" if event_completed else "running"),
        activity_key=scope_activity_key(item_key),
        render_mode="tool_mcp",
    )


def view_image_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    image_artifact_details_fn,
) -> TranscriptEntry | None:
    if str(item.get("tool") or "").strip() != "view_image":
        return None
    if str(item.get("status") or "").strip().lower() != "completed":
        return None
    display_name, artifact_count = image_artifact_details_fn(item)
    if artifact_count <= 0:
        return None
    label = "image artifact" if artifact_count == 1 else "image artifacts"
    subject = display_name or f"{artifact_count} {label}"
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=[
            "• Image ready",
            f"  └ {subject}",
            "    state=image_ready",
        ],
        status="success",
        activity_key=scope_activity_key(item_key),
        render_mode="tool_view_image_ready",
    )


def view_document_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    view_document_extraction_details_fn,
) -> TranscriptEntry | None:
    if str(item.get("tool") or "").strip() != "view_document":
        return None
    if str(item.get("status") or "").strip().lower() != "completed":
        return None
    display_name, extraction_mode, state = view_document_extraction_details_fn(item)
    if not state:
        return None
    subject = display_name or "document"
    detail = "structured content" if extraction_mode == "structured_content" else "text slice"
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=[
            "• Document extracted",
            f"  └ {subject} ({detail})",
            f"    state={state}",
        ],
        status="success",
        activity_key=scope_activity_key(item_key),
        render_mode="tool_view_document_ready",
    )


def input_image_output_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    input_image_output_transport_details_fn,
) -> TranscriptEntry | None:
    display_name, image_count, transport_family, state = input_image_output_transport_details_fn(item)
    if image_count <= 0:
        return None
    label = "image artifact" if image_count == 1 else "image artifacts"
    subject = display_name or f"{image_count} {label}"
    header = "• Image injected"
    if transport_family == "dedicated_tool_native_view_image":
        header = "• Image injected (view_image continuation)"
    elif transport_family == "image_aware_file_read":
        header = "• Image injected (image-aware file read)"
    elif transport_family == "attachment_first_message_native":
        header = "• Image injected (attachment-first)"
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=[
            header,
            f"  └ {subject}",
            f"    state={state or 'image_injected'}",
        ],
        status="success",
        activity_key=scope_activity_key(item_key),
        render_mode="tool_input_image_output",
    )


def document_output_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    document_output_projection_details_fn,
) -> TranscriptEntry | None:
    display_name, projection_mode, state = document_output_projection_details_fn(item)
    if not state:
        return None
    subject = display_name or "document extraction"
    header = "• Document projected"
    if projection_mode == "tool_result_content_block":
        header = "• Document projected (tool result)"
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=[
            header,
            f"  └ {subject}",
            f"    state={state}",
        ],
        status="success",
        activity_key=scope_activity_key(item_key),
        render_mode="tool_document_output",
    )


def tool_event_from_turn_tool_item(item: dict[str, object], *, runtime_service) -> ToolEvent | None:
    return runtime_service.tool_event_from_turn_tool_item(item)
