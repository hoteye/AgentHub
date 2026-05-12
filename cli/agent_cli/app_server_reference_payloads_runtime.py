from __future__ import annotations

from typing import Any

from cli.agent_cli import app_server_reference_payloads_normalization_helpers_runtime as _normalization_helpers
from cli.agent_cli import app_server_reference_payloads_projection_helpers_runtime as _projection_helpers

_snake_to_camel = _normalization_helpers.snake_to_camel
_booleanish = _normalization_helpers.booleanish
_status_value = _normalization_helpers.status_value
_thread_status_value = _normalization_helpers.thread_status_value
_thread_source_value = _normalization_helpers.thread_source_value
_turn_status_value = _normalization_helpers.turn_status_value
_turn_item_type = _normalization_helpers.turn_item_type
_string_list = _normalization_helpers.string_list
_reasoning_content_list = _normalization_helpers.reasoning_content_list
_reasoning_summary_list = _normalization_helpers.reasoning_summary_list
_reasoning_effort_options = _normalization_helpers.reasoning_effort_options
_input_modalities = _normalization_helpers.input_modalities
_reasoning_effort_value = _normalization_helpers.reasoning_effort_value
_camelized_mapping = _normalization_helpers.camelized_mapping
_observable_result_payload = _normalization_helpers.observable_result_payload
_model_list_entry_payload = _normalization_helpers.model_list_entry_payload
_mcp_server_status_entry_payload = _normalization_helpers.mcp_server_status_entry_payload

_canonical_command_execution_turn_item = _projection_helpers.canonical_command_execution_turn_item


def reference_thread_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _projection_helpers.reference_thread_item_payload(item)


def _reference_turn_item(item: dict[str, Any]) -> dict[str, Any]:
    return reference_thread_item_payload(item)


_turn_items_from_events = _projection_helpers.turn_items_from_events


def reference_turn_payload(turn: dict[str, Any], *, include_items: bool = True) -> dict[str, Any]:
    payload = {
        "id": str(turn.get("turn_id") or turn.get("id") or ""),
        "status": _turn_status_value(turn),
        "items": _turn_items_from_events(turn) if include_items else [],
        "error": None,
    }
    status = dict(turn.get("status") or {})
    error_detail = status.get("error")
    if error_detail not in (None, "", False):
        payload["error"] = {"message": str(error_detail)}
    return payload


def reference_turn_runtime_payload(
    *,
    turn_id: str,
    status: str,
) -> dict[str, Any]:
    return {
        "id": str(turn_id or ""),
        "status": _snake_to_camel(str(status or "")),
        "items": [],
        "error": None,
    }


def reference_thread_payload(
    thread: dict[str, Any],
    *,
    include_turns: bool = True,
) -> dict[str, Any]:
    metadata = dict(thread.get("metadata") or {})
    provider_status = dict(metadata.get("provider_status") or {})
    return {
        "id": str(thread.get("id") or thread.get("thread_id") or ""),
        "thread_id": str(thread.get("thread_id") or thread.get("id") or ""),
        "preview": str(thread.get("preview") or ""),
        "ephemeral": bool(thread.get("ephemeral")),
        "modelProvider": str(thread.get("model_provider") or provider_status.get("provider_name") or ""),
        "model_provider": str(thread.get("model_provider") or provider_status.get("provider_name") or ""),
        "createdAt": int(thread.get("created_at_unix") or 0),
        "created_at": int(thread.get("created_at_unix") or 0),
        "updatedAt": int(thread.get("updated_at_unix") or 0),
        "updated_at": int(thread.get("updated_at_unix") or 0),
        "status": _thread_status_value(thread.get("status")),
        "path": str(thread.get("path") or "") or None,
        "cwd": str(thread.get("cwd") or ""),
        "cliVersion": str(thread.get("cli_version") or ""),
        "cli_version": str(thread.get("cli_version") or ""),
        "source": _thread_source_value(thread.get("source")),
        "agentNickname": thread.get("agent_nickname"),
        "agentRole": thread.get("agent_role"),
        "gitInfo": thread.get("git_info"),
        "name": str(thread.get("name") or "").strip() or None,
        "turns": [
            reference_turn_payload(dict(item), include_items=True)
            for item in list(thread.get("turns") or [])
            if isinstance(item, dict)
        ]
        if include_turns
        else [],
    }


def reference_model_list_payload(
    *,
    models: list[dict[str, Any]],
    current_model_tokens: set[str],
    default_reasoning_effort: str,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    data = [
        _model_list_entry_payload(
            item,
            current_model_tokens=current_model_tokens,
            default_reasoning_effort=default_reasoning_effort,
        )
        for item in list(models or [])
    ]
    return {
        "data": data,
        "nextCursor": str(next_cursor) if next_cursor not in (None, "") else None,
    }


def reference_mcp_server_status_payload(
    *,
    entries: list[dict[str, Any]],
    next_cursor: str | None = None,
) -> dict[str, Any]:
    data = [
        _mcp_server_status_entry_payload(entry)
        for entry in list(entries or [])
    ]
    return {
        "data": data,
        "nextCursor": str(next_cursor) if next_cursor not in (None, "") else None,
    }
