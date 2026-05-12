from __future__ import annotations

from typing import Any, Callable, Dict


def turn_context_rollout_from_dict_impl(
    payload: Dict[str, Any],
    *,
    turn_context_input_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    item = dict(payload or {})
    items = [
        turn_context_input_item_from_dict_fn(entry)
        for entry in list(item.get("items") or item.get("input_items") or [])
        if isinstance(entry, dict)
    ]
    if not items:
        for key, source in (
            ("environment_input_items", "environment_context"),
            ("workspace_input_items", "workspace_context"),
        ):
            for entry in list(item.get(key) or []):
                if isinstance(entry, dict):
                    items.append(
                        turn_context_input_item_from_dict_fn(
                            {
                                "source": source,
                                "item": entry,
                            }
                        )
                    )
    network_access_enabled = item.get("network_access_enabled")
    if not isinstance(network_access_enabled, bool):
        network_access_enabled = None
    return {
        "cwd": str(item.get("cwd") or ""),
        "shell": str(item.get("shell") or ""),
        "current_date": str(item.get("current_date") or ""),
        "timezone": str(item.get("timezone") or ""),
        "approval_policy": str(item.get("approval_policy") or ""),
        "sandbox_mode": str(item.get("sandbox_mode") or ""),
        "model": str(item.get("model") or ""),
        "network_access_enabled": network_access_enabled,
        "items": items,
        "reference_context_items": [
            reference_context_item_from_dict_fn(entry)
            for entry in list(item.get("reference_context_items") or [])
            if isinstance(entry, dict)
        ],
        "state": dict(item.get("state") or {}),
    }


def thread_history_turn_from_dict_impl(
    payload: Dict[str, Any],
    *,
    prompt_attachment_from_dict_fn: Callable[[Dict[str, Any]], Any],
    tool_event_from_dict_fn: Callable[[Dict[str, Any]], Any],
    activity_event_from_dict_fn: Callable[[Dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
    response_input_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    item = dict(payload or {})
    return {
        "turn_id": str(item.get("turn_id") or ""),
        "timestamp": str(item.get("timestamp") or ""),
        "user_text": str(item.get("user_text") or ""),
        "commentary_text": str(item.get("commentary_text") or ""),
        "assistant_text": str(item.get("assistant_text") or ""),
        "assistant_history_text": str(item.get("assistant_history_text") or ""),
        "command_display_text": str(item.get("command_display_text") or ""),
        "handled_as_command": bool(item.get("handled_as_command")),
        "status": dict(item.get("status") or {}),
        "protocol_diagnostics": dict(item.get("protocol_diagnostics") or {}),
        "runtime_state": dict(item.get("runtime_state") or {}),
        "attachments": [
            prompt_attachment_from_dict_fn(entry)
            for entry in list(item.get("attachments") or [])
            if isinstance(entry, dict)
        ],
        "tool_events": [
            tool_event_from_dict_fn(entry)
            for entry in list(item.get("tool_events") or [])
            if isinstance(entry, dict)
        ],
        "activity_events": [
            activity_event_from_dict_fn(entry)
            for entry in list(item.get("activity_events") or [])
            if isinstance(entry, dict)
        ],
        "reference_context_items": [
            reference_context_item_from_dict_fn(entry)
            for entry in list(item.get("reference_context_items") or item.get("context_items") or [])
            if isinstance(entry, dict)
        ],
        "response_items": [
            response_input_item_from_dict_fn(entry)
            for entry in list(item.get("response_items") or [])
            if isinstance(entry, dict)
        ],
        "turn_events": [
            dict(entry)
            for entry in list(item.get("turn_events") or [])
            if isinstance(entry, dict)
        ],
    }


def rollout_item_from_dict_impl(
    payload: Dict[str, Any],
    *,
    thread_history_turn_from_dict_fn: Callable[[Dict[str, Any]], Any],
    thread_history_turn_from_legacy_turn_payload_fn: Callable[[Dict[str, Any]], Any],
    turn_context_rollout_from_dict_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    item = dict(payload or {})
    item_type = str(item.get("type") or item.get("item_type") or "").strip()
    turn_payload = item.get("turn")
    turn = None
    turn_context = None
    if isinstance(turn_payload, dict):
        turn = thread_history_turn_from_dict_fn(turn_payload)
    elif item_type == "turn":
        turn = thread_history_turn_from_legacy_turn_payload_fn(item)
    if item_type == "turn_context":
        turn_context = turn_context_rollout_from_dict_fn(item)
    excluded_keys = {"type", "item_type", "thread_id", "timestamp", "turn"}
    if item_type == "turn_context":
        excluded_keys.update(
            {
                "cwd",
                "shell",
                "current_date",
                "timezone",
                "approval_policy",
                "sandbox_mode",
                "model",
                "network_access_enabled",
                "items",
                "input_items",
                "environment_input_items",
                "workspace_input_items",
                "reference_context_items",
                "state",
            }
        )
    return {
        "item_type": item_type,
        "thread_id": str(item.get("thread_id") or ""),
        "timestamp": str(item.get("timestamp") or getattr(turn, "timestamp", "") or ""),
        "payload": {
            key: value
            for key, value in item.items()
            if key not in excluded_keys
        },
        "turn": turn,
        "turn_context": turn_context,
    }
