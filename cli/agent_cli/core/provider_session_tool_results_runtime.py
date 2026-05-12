from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service
from cli.agent_cli.models import (
    FunctionCallOutputPayload,
    ToolEvent,
    tool_event_result_text,
)
from cli.agent_cli.core import provider_session_tool_results_shell_runtime as shell_runtime_service
from cli.agent_cli.tools_core.output_persistence_runtime import (
    ToolOutputPersistenceContext,
    persist_large_tool_output,
)

tool_event_provider_type = shell_runtime_service.tool_event_provider_type
tool_event_provider_raw_item = shell_runtime_service.tool_event_provider_raw_item
shell_output_block = shell_runtime_service.shell_output_block
shell_exit_code = shell_runtime_service.shell_exit_code
shell_exit_code_from_payload = shell_runtime_service.shell_exit_code_from_payload
tool_event_is_shell_like = shell_runtime_service.tool_event_is_shell_like
shell_stdout_text = shell_runtime_service.shell_stdout_text
shell_stderr_text = shell_runtime_service.shell_stderr_text
tool_result_projection_policy = shell_runtime_service.tool_result_projection_policy
shell_running_status = shell_runtime_service.shell_running_status
shell_failure_line = shell_runtime_service.shell_failure_line
shell_summary_text = shell_runtime_service.shell_summary_text
shell_background_line = shell_runtime_service.shell_background_line
shell_codex_background_line = shell_runtime_service.shell_codex_background_line
shell_codex_normalized_explicit_output = shell_runtime_service.shell_codex_normalized_explicit_output
shell_codex_status_line = shell_runtime_service.shell_codex_status_line
shell_codex_fallback_line = shell_runtime_service.shell_codex_fallback_line
shell_explicit_fallback_text = shell_runtime_service.shell_explicit_fallback_text
inline_apply_patch_text = shell_runtime_service.inline_apply_patch_text
codex_apply_patch_warning_item = shell_runtime_service.codex_apply_patch_warning_item
shell_tool_result_payload = shell_runtime_service.shell_tool_result_payload
shell_tool_result_items = shell_runtime_service.shell_tool_result_items


def tool_output_persistence_context(
    *,
    tool_result_projection_policy: str = "",
    workspace_root: str | None = None,
    tool_output_thread_id: str | None = None,
) -> ToolOutputPersistenceContext:
    return ToolOutputPersistenceContext(
        tool_result_projection_policy=str(tool_result_projection_policy or "").strip(),
        workspace_root=str(workspace_root or "").strip(),
        thread_id=str(tool_output_thread_id or "").strip(),
    )


def persist_large_payload_if_needed(
    payload: FunctionCallOutputPayload,
    *,
    call_id: str,
    tool_result_projection_policy: str = "",
    workspace_root: str | None = None,
    tool_output_thread_id: str | None = None,
) -> FunctionCallOutputPayload:
    text = payload.to_text()
    if not text:
        return payload
    persisted = persist_large_tool_output(
        text,
        call_id=call_id,
        context=tool_output_persistence_context(
            tool_result_projection_policy=tool_result_projection_policy,
            workspace_root=workspace_root,
            tool_output_thread_id=tool_output_thread_id,
        ),
    )
    if persisted.model_output == text:
        return payload
    return FunctionCallOutputPayload.from_output(persisted.model_output, success=payload.success)


def tool_result_payload(
    command_text: Optional[str],
    assistant_text: str,
    events: List[ToolEvent],
) -> FunctionCallOutputPayload:
    last_event = events[-1] if events else None
    payload = last_event.payload if isinstance(getattr(last_event, "payload", None), dict) else {}
    explicit_output = payload.get("function_call_output") if isinstance(payload, dict) else None
    if explicit_output is not None:
        success = bool(last_event.ok) if last_event is not None else None
        return FunctionCallOutputPayload.from_output(explicit_output, success=success)
    projected_output = models_mapping_runtime_service.view_document_output_projection(payload)
    if projected_output is not None:
        success = bool(last_event.ok) if last_event is not None else None
        return FunctionCallOutputPayload.from_output(projected_output.get("output"), success=success)
    if last_event is not None:
        success = bool(last_event.ok)
        result_text = tool_event_result_text(last_event)
        if result_text:
            return FunctionCallOutputPayload.from_output(result_text, success=success)
    if payload:
        structured_payload = dict(payload)
        if last_event is not None:
            structured_payload.setdefault("ok", bool(last_event.ok))
            if str(getattr(last_event, "name", "") or "").strip():
                structured_payload.setdefault("tool_name", str(last_event.name))
            if str(getattr(last_event, "summary", "") or "").strip():
                structured_payload.setdefault("summary", str(last_event.summary))
        success = bool(last_event.ok) if last_event is not None else None
        return FunctionCallOutputPayload.from_output(structured_payload, success=success)
    text = str(assistant_text or "").strip()
    if not text:
        text = str(payload.get("error") or "").strip()
    if not text and last_event is not None:
        text = str(last_event.summary or "").strip()
    if not text:
        text = str(command_text or "").strip()
    success = bool(last_event.ok) if last_event is not None else bool(command_text or text)
    return FunctionCallOutputPayload.from_output(text, success=success)


def default_tool_result_items(
    *,
    call_id: str,
    command_text: Optional[str],
    assistant_text: str,
    events: List[ToolEvent],
    tool_result_projection_policy: str = "",
    workspace_root: str | None = None,
    tool_output_thread_id: str | None = None,
) -> List[Dict[str, Any]]:
    last_event = events[-1] if events else None
    provider_item_type = tool_event_provider_type(last_event)
    if provider_item_type in {"shell_call", "local_shell_call"}:
        return shell_tool_result_items(call_id=call_id, events=events)
    payload = None
    normalized_policy = str(tool_result_projection_policy or "").strip().lower()
    if normalized_policy in {"claude_like", "codex_like"}:
        payload = shell_tool_result_payload(
            command_text,
            assistant_text,
            events,
            tool_result_projection_policy=normalized_policy,
        )
    if payload is None:
        payload = tool_result_payload(command_text, assistant_text, events)
    payload = persist_large_payload_if_needed(
        payload,
        call_id=call_id,
        tool_result_projection_policy=tool_result_projection_policy,
        workspace_root=workspace_root,
        tool_output_thread_id=tool_output_thread_id,
    )
    output_item_type = "custom_tool_call_output" if provider_item_type == "custom_tool_call" else "function_call_output"
    item: Dict[str, Any] = {
        "type": output_item_type,
        "call_id": call_id,
        "output": payload.wire_value(),
    }
    raw_payload = dict(last_event.payload or {}) if last_event is not None else {}
    document_projection = models_mapping_runtime_service.view_document_output_projection(raw_payload)
    if document_projection is not None and bool(document_projection.get("model_visible")):
        projection_mode = str(document_projection.get("projection_mode") or "").strip()
        projection_state = str(document_projection.get("projection_state") or "").strip()
        projection_subject = str(document_projection.get("subject") or "").strip()
        if projection_mode:
            item["document_projection_mode"] = projection_mode
        if projection_state:
            item["document_projection_state"] = projection_state
        if projection_subject:
            item["document_projection_subject"] = projection_subject
    if payload.success is not None:
        item["success"] = payload.success
    warning_item = codex_apply_patch_warning_item(
        command_text=command_text,
        tool_event=last_event,
        tool_result_projection_policy=tool_result_projection_policy,
    )
    return [warning_item, item] if warning_item is not None else [item]
