from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import (
    ActivityEvent,
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    ToolEvent,
    default_response_items,
)


def dedupe_reference_context_items(items: List[ReferenceContextItem]) -> List[ReferenceContextItem]:
    seen: set[tuple[str, str, str, str, str, str, str, str]] = set()
    deduped: List[ReferenceContextItem] = []
    for item in items:
        metadata_text = json.dumps(dict(item.metadata or {}), ensure_ascii=False, sort_keys=True)
        key = (
            str(item.item_type or ""),
            str(item.source or ""),
            str(item.label or ""),
            str(item.path or ""),
            str(item.uri or ""),
            str(item.ref or ""),
            str(item.description or ""),
            metadata_text,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def reference_context_items_from_tool_event(event: ToolEvent) -> List[ReferenceContextItem]:
    payload = dict(event.payload or {})
    tool_name = str(event.name or "").strip()
    items: List[ReferenceContextItem] = []
    if tool_name in {"file_read", "read_file"}:
        path_text = str(payload.get("path") or payload.get("file_path") or "").strip()
        if path_text:
            items.append(
                ReferenceContextItem(
                    item_type="file",
                    source=f"tool:{tool_name}",
                    label=Path(path_text).name or path_text,
                    path=path_text,
                    description="workspace_file",
                    metadata={"tool_name": tool_name},
                )
            )
    elif tool_name in {"open", "click", "web_fetch"}:
        uri = str(payload.get("final_url") or payload.get("url") or "").strip()
        ref = str(payload.get("ref") or payload.get("ref_id") or "").strip()
        label = str(payload.get("title") or payload.get("page_title") or uri or ref).strip()
        if uri or ref:
            items.append(
                ReferenceContextItem(
                    item_type="web_page",
                    source=f"tool:{tool_name}",
                    label=label,
                    uri=uri,
                    ref=ref,
                    description="retrieved_page",
                    metadata={"tool_name": tool_name},
                )
            )
    return items


def reference_context_items_from_response(
    response: PromptResponse,
    *,
    reference_context_items_from_tool_event_fn: Callable[[ToolEvent], List[ReferenceContextItem]] = reference_context_items_from_tool_event,
    dedupe_reference_context_items_fn: Callable[[List[ReferenceContextItem]], List[ReferenceContextItem]] = dedupe_reference_context_items,
) -> List[ReferenceContextItem]:
    items: List[ReferenceContextItem] = []
    for entry in list(response.reference_context_items or []):
        if isinstance(entry, ReferenceContextItem):
            items.append(ReferenceContextItem.from_dict(entry.to_dict()))
        elif isinstance(entry, dict):
            items.append(ReferenceContextItem.from_dict(entry))
    for attachment in list(response.attachments or []):
        items.append(ReferenceContextItem.from_attachment(attachment))
    for event in list(response.tool_events or []):
        items.extend(reference_context_items_from_tool_event_fn(event))
    return dedupe_reference_context_items_fn(items)


def history_turn_from_response(
    response: PromptResponse,
    *,
    timestamp: str,
    assistant_history_text: str,
    canonical_turn_events_fn: Callable[[PromptResponse, List[ResponseInputItem]], List[Dict[str, Any]]],
    runtime_state: Optional[Dict[str, Any]] = None,
    reference_context_items_from_tool_event_fn: Callable[[ToolEvent], List[ReferenceContextItem]] = reference_context_items_from_tool_event,
    dedupe_reference_context_items_fn: Callable[[List[ReferenceContextItem]], List[ReferenceContextItem]] = dedupe_reference_context_items,
    attachment_to_dict_fn: Callable[[PromptAttachment], Dict[str, Any]] | None = None,
    tool_event_to_dict_fn: Callable[[ToolEvent], Dict[str, Any]] | None = None,
    activity_event_to_dict_fn: Callable[[ActivityEvent], Dict[str, Any]] | None = None,
) -> ThreadHistoryTurn:
    response_items = [
        ResponseInputItem.from_dict(item.to_dict())
        for item in list(
            response.response_items
            or default_response_items(
                commentary_text=str(response.commentary_text or ""),
                assistant_text=str(response.assistant_text or ""),
            )
        )
    ]
    if attachment_to_dict_fn is None:
        def attachment_to_dict_fn(item: PromptAttachment) -> Dict[str, Any]:
            return item.to_dict()
    if tool_event_to_dict_fn is None:
        def tool_event_to_dict_fn(item: ToolEvent) -> Dict[str, Any]:
            return item.to_dict()
    if activity_event_to_dict_fn is None:
        def activity_event_to_dict_fn(item: ActivityEvent) -> Dict[str, Any]:
            return item.to_dict()
    return ThreadHistoryTurn(
        turn_id=uuid.uuid4().hex,
        timestamp=timestamp,
        user_text=str(response.user_text or ""),
        commentary_text=str(response.commentary_text or ""),
        assistant_text=str(response.assistant_text or ""),
        assistant_history_text=assistant_history_text,
        command_display_text=str(getattr(response, "command_display_text", "") or ""),
        handled_as_command=bool(response.handled_as_command),
        status=dict(response.status or {}),
        protocol_diagnostics=dict(response.protocol_diagnostics or {}),
        runtime_state=dict(runtime_state or {}),
        attachments=[PromptAttachment.from_dict(attachment_to_dict_fn(item)) for item in response.attachments],
        tool_events=[ToolEvent.from_dict(tool_event_to_dict_fn(item)) for item in response.tool_events],
        activity_events=[ActivityEvent.from_dict(activity_event_to_dict_fn(item)) for item in response.activity_events],
        reference_context_items=reference_context_items_from_response(
            response,
            reference_context_items_from_tool_event_fn=reference_context_items_from_tool_event_fn,
            dedupe_reference_context_items_fn=dedupe_reference_context_items_fn,
        ),
        response_items=response_items,
        turn_events=canonical_turn_events_fn(response, response_items),
    )


def rollout_causality_payload(
    response: PromptResponse,
    *,
    runtime_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = [
        _dict_value(response.status),
        _dict_value(runtime_state),
    ]
    for tool_event in list(response.tool_events or []):
        payload = _dict_value(getattr(tool_event, "payload", None))
        if not payload:
            continue
        records.append(payload)
        metadata = _dict_value(payload.get("metadata"))
        if metadata:
            records.append(metadata)
            causality = _dict_value(metadata.get("causality"))
            if causality:
                records.append(causality)
        causality = _dict_value(payload.get("causality"))
        if causality:
            records.append(causality)
    trace_id = _first_text(
        *[
            _first_text(item.get("trace_id"), item.get("traceId"))
            for item in records
        ]
    )
    workflow_run_id = _first_text(
        *[
            _first_text(item.get("workflow_run_id"), item.get("workflowRunId"))
            for item in records
        ]
    )
    payload: Dict[str, Any] = {}
    if trace_id:
        payload["trace_id"] = trace_id
    if workflow_run_id:
        payload["workflow_run_id"] = workflow_run_id
    return payload


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _dict_value(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}
