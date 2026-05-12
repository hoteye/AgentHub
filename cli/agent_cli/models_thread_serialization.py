from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli import models_thread_serialization_helpers as serialization_helpers


def response_input_item_from_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(payload or {})
    item_type = str(item.get("type") or item.get("item_type") or "message").strip() or "message"
    role = str(item.get("role") or "").strip()
    content = item.get("content")
    content_present = "content" in item
    if isinstance(content, list):
        normalized_content: Any = [dict(entry) for entry in content if isinstance(entry, dict)]
    elif isinstance(content, dict):
        normalized_content = dict(content)
    elif isinstance(content, str):
        normalized_content = content
    elif content is None and content_present:
        normalized_content = None
    else:
        normalized_content = ""
    return {
        "item_type": item_type,
        "role": role,
        "content": normalized_content,
        "content_present": content_present,
        "extra": {
            key: value
            for key, value in item.items()
            if key not in {"type", "item_type", "role", "content"}
        },
    }


def response_input_item_to_dict(item_type: str, role: str, content: Any, content_present: bool, extra: Dict[str, Any]) -> Dict[str, Any]:
    extra_dict = dict(extra or {})
    if item_type == "reasoning":
        extra_dict = {k: v for k, v in extra_dict.items() if k not in {"id", "status"}}

    payload: Dict[str, Any] = {
        "type": item_type,
        **extra_dict,
    }
    if role:
        payload["role"] = role
    if isinstance(content, list):
        payload["content"] = [dict(entry) for entry in content if isinstance(entry, dict)]
    elif isinstance(content, dict):
        payload["content"] = dict(content)
    elif content is None:
        if content_present:
            payload["content"] = None
    elif str(content or "").strip() or content_present:
        payload["content"] = str(content or "")
    return payload


def turn_context_input_item_from_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    entry = dict(payload or {})
    item_payload = entry.get("item")
    if not isinstance(item_payload, dict):
        item_payload = {
            key: value
            for key, value in entry.items()
            if key != "source"
        }
    return {
        "source": str(entry.get("source") or ""),
        "item_payload": dict(item_payload or {}),
    }


def turn_context_input_item_to_dict(*, source: str, item_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "item": dict(item_payload or {}),
    }
    if source:
        payload["source"] = source
    return payload


def turn_context_rollout_from_dict(
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


def turn_context_rollout_to_dict(
    *,
    cwd: str,
    shell: str,
    current_date: str,
    timezone: str,
    approval_policy: str,
    sandbox_mode: str,
    model: str,
    network_access_enabled: bool | None,
    items: List[Any],
    reference_context_items: List[Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "items": [item.to_dict() for item in items],
        "reference_context_items": [item.to_dict() for item in reference_context_items],
        "state": dict(state or {}),
    }
    if cwd:
        payload["cwd"] = cwd
    if shell:
        payload["shell"] = shell
    if current_date:
        payload["current_date"] = current_date
    if timezone:
        payload["timezone"] = timezone
    if approval_policy:
        payload["approval_policy"] = approval_policy
    if sandbox_mode:
        payload["sandbox_mode"] = sandbox_mode
    if model:
        payload["model"] = model
    if network_access_enabled is not None:
        payload["network_access_enabled"] = network_access_enabled
    return payload


def thread_history_turn_from_dict(
    payload: Dict[str, Any],
    *,
    prompt_attachment_from_dict_fn: Callable[[Dict[str, Any]], Any],
    tool_event_from_dict_fn: Callable[[Dict[str, Any]], Any],
    activity_event_from_dict_fn: Callable[[Dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
    response_input_item_from_dict_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    return serialization_helpers.thread_history_turn_from_dict_impl(
        payload,
        prompt_attachment_from_dict_fn=prompt_attachment_from_dict_fn,
        tool_event_from_dict_fn=tool_event_from_dict_fn,
        activity_event_from_dict_fn=activity_event_from_dict_fn,
        reference_context_item_from_dict_fn=reference_context_item_from_dict_fn,
        response_input_item_from_dict_fn=response_input_item_from_dict_fn,
    )


def thread_history_turn_to_dict(
    *,
    turn_id: str,
    timestamp: str,
    user_text: str,
    commentary_text: str,
    assistant_text: str,
    assistant_history_text: str,
    command_display_text: str,
    handled_as_command: bool,
    status: Dict[str, Any],
    protocol_diagnostics: Dict[str, Any],
    runtime_state: Dict[str, Any],
    attachments: List[Any],
    tool_events: List[Any],
    activity_events: List[Any],
    reference_context_items: List[Any],
    response_items: List[Any],
    turn_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "turn_id": turn_id,
        "timestamp": timestamp,
        "user_text": user_text,
        "commentary_text": commentary_text,
        "assistant_text": assistant_text,
        "assistant_history_text": assistant_history_text,
        "command_display_text": command_display_text,
        "handled_as_command": handled_as_command,
        "status": dict(status or {}),
        "protocol_diagnostics": dict(protocol_diagnostics or {}),
        "runtime_state": dict(runtime_state or {}),
        "attachments": [item.to_dict() for item in attachments],
        "tool_events": [item.to_dict() for item in tool_events],
        "activity_events": [item.to_dict() for item in activity_events],
        "reference_context_items": [item.to_dict() for item in reference_context_items],
        "response_items": [item.to_dict() for item in response_items],
        "turn_events": [dict(item) for item in turn_events],
    }


def thread_history_turn_from_legacy_turn_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(payload or {})
    return {
        "timestamp": item.get("timestamp"),
        "user_text": item.get("user_text"),
        "commentary_text": item.get("commentary_text"),
        "assistant_text": item.get("assistant_text"),
        "assistant_history_text": item.get("assistant_history_text"),
        "command_display_text": item.get("command_display_text"),
        "handled_as_command": item.get("handled_as_command"),
        "status": item.get("status"),
        "protocol_diagnostics": item.get("protocol_diagnostics"),
        "runtime_state": item.get("runtime_state"),
        "attachments": item.get("attachments"),
        "tool_events": item.get("tool_events"),
        "activity_events": item.get("activity_events"),
        "reference_context_items": item.get("reference_context_items") or item.get("context_items"),
        "response_items": item.get("response_items"),
        "turn_events": item.get("turn_events"),
    }


def rollout_item_from_dict(
    payload: Dict[str, Any],
    *,
    thread_history_turn_from_dict_fn: Callable[[Dict[str, Any]], Any],
    thread_history_turn_from_legacy_turn_payload_fn: Callable[[Dict[str, Any]], Any],
    turn_context_rollout_from_dict_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    return serialization_helpers.rollout_item_from_dict_impl(
        payload,
        thread_history_turn_from_dict_fn=thread_history_turn_from_dict_fn,
        thread_history_turn_from_legacy_turn_payload_fn=thread_history_turn_from_legacy_turn_payload_fn,
        turn_context_rollout_from_dict_fn=turn_context_rollout_from_dict_fn,
    )


def rollout_item_to_dict(
    *,
    item_type: str,
    thread_id: str,
    timestamp: str,
    payload: Dict[str, Any],
    turn: Any,
    turn_context: Any,
) -> Dict[str, Any]:
    base = {
        "type": item_type,
        "thread_id": thread_id,
        "timestamp": timestamp,
        **dict(payload or {}),
    }
    if turn_context is not None:
        base.update(turn_context.to_dict())
    if turn is None:
        return base
    turn_payload = turn.to_dict()
    base["turn"] = turn_payload
    base.update(
        {
            "user_text": turn_payload["user_text"],
            "commentary_text": turn_payload["commentary_text"],
            "assistant_text": turn_payload["assistant_text"],
            "assistant_history_text": turn_payload["assistant_history_text"],
            "command_display_text": turn_payload["command_display_text"],
            "attachments": turn_payload["attachments"],
            "handled_as_command": turn_payload["handled_as_command"],
            "status": turn_payload["status"],
            "protocol_diagnostics": turn_payload["protocol_diagnostics"],
            "runtime_state": turn_payload["runtime_state"],
            "tool_events": turn_payload["tool_events"],
            "activity_events": turn_payload["activity_events"],
            "reference_context_items": turn_payload["reference_context_items"],
            "response_items": turn_payload["response_items"],
        }
    )
    return base
