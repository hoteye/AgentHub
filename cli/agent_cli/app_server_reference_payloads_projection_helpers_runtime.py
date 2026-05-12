from __future__ import annotations

from typing import Any

from cli.agent_cli.app_server_reference_payloads_normalization_helpers_runtime import (
    camelized_mapping,
    observable_result_payload,
    reasoning_content_list,
    reasoning_summary_list,
    status_value,
    turn_item_type,
)


def canonical_command_execution_turn_item(item: dict[str, Any]) -> dict[str, Any] | None:
    from cli.agent_cli.models_turn_events import canonical_command_execution_item_from_provider_shell_payload

    payload = canonical_command_execution_item_from_provider_shell_payload(
        item,
        item_id=str(item.get("call_id") or item.get("id") or "").strip() or "command_execution",
    )
    if payload is None:
        return None
    command_text = str(payload.get("command") or "").strip()
    if not command_text:
        command_text = str(item.get("command") or "").strip()
        if command_text:
            payload["command"] = command_text
    return payload


def reference_thread_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    from cli.agent_cli.models_turn_events_runtime import plugin_observability_from_turn_item

    payload = canonical_command_execution_turn_item(dict(item or {})) or dict(item or {})
    normalized = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "aggregated_output",
            "exit_code",
            "provider_item_id",
            "process_id",
            "duration_ms",
            "command_actions",
            "plugin_observability",
        }
    }
    item_type = turn_item_type(str(payload.get("type") or ""))
    normalized["type"] = item_type
    plugin_observability = plugin_observability_from_turn_item(payload)
    if plugin_observability is not None:
        normalized["pluginObservability"] = camelized_mapping(plugin_observability)
    if "status" in payload:
        normalized["status"] = status_value(payload.get("status"))
    if "aggregated_output" in payload:
        normalized["aggregatedOutput"] = payload.get("aggregated_output")
    if "exit_code" in payload:
        normalized["exitCode"] = payload.get("exit_code")
    if "provider_item_id" in payload:
        normalized["providerItemId"] = payload.get("provider_item_id")
    if "process_id" in payload:
        normalized["processId"] = payload.get("process_id")
    if "duration_ms" in payload:
        normalized["durationMs"] = payload.get("duration_ms")
    if "command_actions" in payload:
        normalized["commandActions"] = list(payload.get("command_actions") or [])
    if isinstance(normalized.get("result"), dict):
        result = dict(normalized["result"])
        if "structured_content" in result:
            result["structuredContent"] = result.pop("structured_content")
        normalized["result"] = observable_result_payload(result)
    if item_type == "agentMessage":
        normalized["text"] = str(payload.get("text") or "")
        normalized["phase"] = normalized.get("phase")
    elif item_type == "reasoning":
        normalized["summary"] = reasoning_summary_list(payload)
        normalized["content"] = reasoning_content_list(payload)
        normalized.pop("text", None)
    elif item_type == "commandExecution":
        normalized["command"] = str(payload.get("command") or "")
        normalized["cwd"] = str(payload.get("cwd") or "")
        normalized["processId"] = normalized.get("processId")
        normalized["commandActions"] = list(normalized.get("commandActions") or [])
        normalized["aggregatedOutput"] = normalized.get("aggregatedOutput")
        normalized["exitCode"] = normalized.get("exitCode")
        normalized["durationMs"] = normalized.get("durationMs")
    elif item_type == "plan":
        normalized["text"] = str(payload.get("text") or "")
    elif item_type == "mcpToolCall":
        normalized["durationMs"] = normalized.get("durationMs")
    return normalized


def _merge_command_execution_payloads(
    previous_payload: dict[str, Any],
    next_payload: dict[str, Any],
) -> dict[str, Any]:
    merged_payload = dict(previous_payload)
    merged_payload.update(next_payload)
    for key in ("command", "cwd", "aggregatedOutput", "processId", "durationMs"):
        if merged_payload.get(key) in (None, "", [], {}):
            merged_payload[key] = previous_payload.get(key)
    if not merged_payload.get("commandActions"):
        merged_payload["commandActions"] = list(previous_payload.get("commandActions") or [])
    return merged_payload


def turn_items_from_events(turn: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    turn_id = str(turn.get("turn_id") or "").strip()
    user_text = str(turn.get("user_text") or "").strip()
    if user_text:
        items.append(
            {
                "id": f"{turn_id or 'turn'}_user",
                "type": "userMessage",
                "content": [{"type": "text", "text": user_text, "textElements": []}],
            }
        )
    latest_by_id: dict[str, dict[str, Any]] = {}
    item_order: list[str] = []
    for raw_event in list(turn.get("turn_events") or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("call_id") or "").strip()
        if not item_id:
            continue
        if item_id not in latest_by_id:
            item_order.append(item_id)
        next_payload = reference_thread_item_payload(item)
        previous_payload = latest_by_id.get(item_id)
        if (
            isinstance(previous_payload, dict)
            and str(previous_payload.get("type") or "").strip() == "commandExecution"
            and str(next_payload.get("type") or "").strip() == "commandExecution"
        ):
            next_payload = _merge_command_execution_payloads(previous_payload, next_payload)
        latest_by_id[item_id] = next_payload
    for item_id in item_order:
        payload = latest_by_id.get(item_id)
        if payload is not None:
            items.append(payload)
    if len(items) == 1:
        assistant_text = str(turn.get("assistant_text") or "").strip()
        if assistant_text:
            items.append(
                {
                    "id": f"{turn_id or 'turn'}_assistant",
                    "type": "agentMessage",
                    "text": assistant_text,
                }
            )
    return items
