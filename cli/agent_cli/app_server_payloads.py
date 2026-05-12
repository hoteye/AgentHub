from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.app_server_reference_payloads_runtime import (
    reference_mcp_server_status_payload as _reference_mcp_server_status_payload,
    reference_model_list_payload as _reference_model_list_payload,
    reference_thread_item_payload as _reference_thread_item_payload,
    reference_thread_payload as _reference_thread_payload,
    reference_turn_payload as _reference_turn_payload,
    reference_turn_runtime_payload as _reference_turn_runtime_payload,
)
from cli.agent_cli.models import PromptAttachment


def activity_event_to_dict(item: Any) -> dict[str, Any]:
    return {
        "title": item.title,
        "status": item.status,
        "detail": item.detail,
        "kind": item.kind,
    }


def tool_event_to_dict(item: Any) -> dict[str, Any]:
    return {
        "name": item.name,
        "ok": item.ok,
        "summary": item.summary,
        "payload": dict(item.payload or {}),
    }


def thread_history_turn_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item or {})
    payload["status"] = dict(payload.get("status") or {})
    payload["protocol_diagnostics"] = dict(payload.get("protocol_diagnostics") or {})
    payload["runtime_state"] = dict(payload.get("runtime_state") or {})
    payload["attachments"] = [dict(entry) for entry in list(payload.get("attachments") or []) if isinstance(entry, dict)]
    payload["tool_events"] = [dict(entry) for entry in list(payload.get("tool_events") or []) if isinstance(entry, dict)]
    payload["activity_events"] = [
        dict(entry)
        for entry in list(payload.get("activity_events") or [])
        if isinstance(entry, dict)
    ]
    payload["reference_context_items"] = [
        dict(entry)
        for entry in list(payload.get("reference_context_items") or [])
        if isinstance(entry, dict)
    ]
    payload["response_items"] = [dict(entry) for entry in list(payload.get("response_items") or []) if isinstance(entry, dict)]
    payload["turn_events"] = [dict(entry) for entry in list(payload.get("turn_events") or []) if isinstance(entry, dict)]
    return payload


def thread_response_payload(
    runtime: Any,
    thread: dict[str, Any],
    *,
    resume_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "thread": dict(thread or {}),
        **dict(runtime.response_runtime_snapshot() or {}),
    }
    if resume_diagnostics is not None:
        payload["resume_diagnostics"] = dict(resume_diagnostics or {})
    return payload


def thread_resume_diagnostics(
    payload: dict[str, Any],
    *,
    requested_sources: dict[str, Any],
    thread: dict[str, Any],
) -> dict[str, Any]:
    selected_source = str(payload.get("resume_source") or "thread_id").strip() or "thread_id"
    precedence = ["history", "path", "thread_id"]
    requested_thread_id = str(requested_sources.get("thread_id") or "").strip() or None
    requested_path = str(requested_sources.get("path") or "").strip() or None
    history_count = int(requested_sources.get("history_count") or 0)
    available_sources = {
        "history": history_count > 0,
        "path": bool(requested_path),
        "thread_id": bool(requested_thread_id),
    }
    ignored_sources = [source for source in precedence if available_sources.get(source) and source != selected_source]
    return {
        "selected_source": selected_source,
        "selected_thread_id": str(thread.get("thread_id") or ""),
        "selected_path": thread.get("path"),
        "precedence": precedence,
        "requested": {
            "thread_id": requested_thread_id,
            "path": requested_path,
            "history_count": history_count,
        },
        "ignored_sources": ignored_sources,
    }


def thread_resume_payload(
    runtime: Any,
    payload: dict[str, Any],
    *,
    requested_sources: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(payload or {})
    thread = runtime.describe_thread(
        dict(normalized.get("thread") or {}),
        status="idle",
        turns=[
            thread_history_turn_payload(entry)
            for entry in list(normalized.get("turns") or [])
            if isinstance(entry, dict)
        ],
    )
    normalized.update(thread_response_payload(runtime, thread))
    normalized["history"] = [
        dict(entry)
        for entry in list(normalized.get("history") or [])
        if isinstance(entry, dict)
    ]
    normalized["base_history"] = [
        dict(entry)
        for entry in list(normalized.get("base_history") or [])
        if isinstance(entry, dict)
    ]
    normalized["planner_history"] = [
        dict(entry)
        for entry in list(normalized.get("planner_history") or [])
        if isinstance(entry, dict)
    ]
    normalized["planner_input_items"] = [
        dict(entry)
        for entry in list(normalized.get("planner_input_items") or [])
        if isinstance(entry, dict)
    ]
    normalized["turns"] = [
        thread_history_turn_payload(entry)
        for entry in list(normalized.get("turns") or [])
        if isinstance(entry, dict)
    ]
    normalized["rollout_items"] = [
        dict(entry)
        for entry in list(normalized.get("rollout_items") or [])
        if isinstance(entry, dict)
    ]
    normalized["context_items"] = [
        dict(entry)
        for entry in list(normalized.get("context_items") or [])
        if isinstance(entry, dict)
    ]
    normalized["state"] = dict(normalized.get("state") or {})
    normalized["resume_diagnostics"] = thread_resume_diagnostics(
        normalized,
        requested_sources=requested_sources,
        thread=thread,
    )
    return normalized


def route_decision_to_dict(item: Any) -> dict[str, Any]:
    return {
        "targetKind": item.target_kind,
        "pluginName": item.plugin_name,
        "workflowName": item.workflow_name,
        "reason": item.reason,
        "trigger": gateway_item_to_dict(item.trigger),
    }


def gateway_dispatch_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": gateway_item_to_dict(result.get("event")),
        "decision": route_decision_to_dict(result["decision"]),
        "workflowRun": gateway_item_to_dict(result.get("workflow_run")),
        "auditRecords": [gateway_item_to_dict(item) for item in result.get("audit_records") or []],
    }


def gateway_item_to_dict(item: Any) -> Any:
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return item


def reference_thread_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _reference_thread_item_payload(item)


def reference_turn_payload(turn: dict[str, Any], *, include_items: bool = True) -> dict[str, Any]:
    return _reference_turn_payload(turn, include_items=include_items)


def reference_turn_runtime_payload(
    *,
    turn_id: str,
    status: str,
) -> dict[str, Any]:
    return _reference_turn_runtime_payload(turn_id=turn_id, status=status)


def reference_thread_payload(
    thread: dict[str, Any],
    *,
    include_turns: bool = True,
) -> dict[str, Any]:
    return _reference_thread_payload(thread, include_turns=include_turns)


def reference_model_list_payload(
    *,
    models: list[dict[str, Any]],
    current_model_tokens: set[str],
    default_reasoning_effort: str,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    return _reference_model_list_payload(
        models=models,
        current_model_tokens=current_model_tokens,
        default_reasoning_effort=default_reasoning_effort,
        next_cursor=next_cursor,
    )


def reference_mcp_server_status_payload(
    *,
    entries: list[dict[str, Any]],
    next_cursor: str | None = None,
) -> dict[str, Any]:
    return _reference_mcp_server_status_payload(entries=entries, next_cursor=next_cursor)


def prompt_attachment_for_turn_input(path_text: str) -> PromptAttachment:
    return PromptAttachment.from_path(path_text, source="app_server_turn_input")


def thread_path_exists(thread: dict[str, Any]) -> bool:
    path_text = str(thread.get("path") or "").strip()
    if not path_text:
        return False
    try:
        return Path(path_text).exists()
    except OSError:
        return False
