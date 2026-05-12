from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.environment_context import environment_contract
from cli.agent_cli.workspace_context import workspace_contract


_CANONICAL_RESPONSE_ITEM_TYPES = {
    "message",
    "reasoning",
    "function_call",
    "function_call_output",
}
_IGNORED_PROTOCOL_METADATA_KEYS = {
    "annotations",
    "logprobs",
}


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_assistant_text(payload: dict[str, Any] | None) -> str:
    return str((payload or {}).get("assistant_text") or "").strip()


def _payload_thread_id(payload: dict[str, Any] | None) -> str:
    status = (payload or {}).get("status")
    if not isinstance(status, dict):
        return ""
    value = str(status.get("thread_id") or "").strip()
    if value in {"", "-", "None", "null"}:
        return ""
    return value


def _payload_provider_runtime_state(payload: dict[str, Any] | None) -> str:
    status = (payload or {}).get("status")
    if not isinstance(status, dict):
        return ""
    return str(status.get("provider_runtime_state") or "").strip()


def _payload_protocol_diagnostics(payload: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = (payload or {}).get("protocol_diagnostics")
    return dict(diagnostics) if isinstance(diagnostics, dict) else {}


def _payload_request_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = _payload_protocol_diagnostics(payload)
    request_contract = diagnostics.get("request_contract")
    return dict(request_contract) if isinstance(request_contract, dict) else {}


def _payload_environment_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    request_contract = _payload_request_contract(payload)
    return environment_contract(request_contract.get("environment"))


def _payload_workspace_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    request_contract = _payload_request_contract(payload)
    return workspace_contract(request_contract.get("workspace"))


def _payload_prelude_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    request_contract = _payload_request_contract(payload)
    prelude = request_contract.get("prelude")
    return dict(prelude) if isinstance(prelude, dict) else {}


def _payload_protocol_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = _payload_protocol_diagnostics(payload)
    protocol_path = diagnostics.get("protocol_path")
    return dict(protocol_path) if isinstance(protocol_path, dict) else {}


def _payload_tool_signatures(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    tools = []
    for item in list((payload or {}).get("tool_events") or []):
        if not isinstance(item, dict):
            continue
        tools.append(
            {
                "name": str(item.get("name") or "").strip(),
                "ok": bool(item.get("ok")),
            }
        )
    return tools


def _payload_tool_names(payload: dict[str, Any] | None) -> list[str]:
    return [str(item.get("name") or "").strip() for item in _payload_tool_signatures(payload)]


def _payload_response_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = [
        dict(item)
        for item in list((payload or {}).get("response_items") or [])
        if isinstance(item, dict)
    ]
    return _canonical_response_items_for_protocol(items)


def _function_call_command(item: dict[str, Any]) -> str:
    if str(item.get("type") or item.get("item_type") or "").strip() != "function_call":
        return ""
    arguments = item.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(arguments, dict):
        return ""
    return str(arguments.get("cmd") or arguments.get("command") or "").strip()


def _strip_shell_command_quotes(command: str) -> str:
    normalized = str(command or "").strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        return normalized[1:-1].strip()
    return normalized


def _unwrapped_shell_command(command: str) -> str:
    normalized = str(command or "").strip()
    for prefix in (
        "/bin/bash -lc ",
        "bash -lc ",
        "/bin/sh -lc ",
        "sh -lc ",
    ):
        if normalized.startswith(prefix):
            return _strip_shell_command_quotes(normalized[len(prefix) :])
    return normalized


def _commands_match_shell_wrapper(shorthand: str, wrapped: str) -> bool:
    normalized_shorthand = str(shorthand or "").strip()
    if not normalized_shorthand:
        return False
    return normalized_shorthand == _unwrapped_shell_command(wrapped)


def _canonical_response_items_for_protocol(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        if index + 2 < len(items):
            first = items[index]
            second = items[index + 1]
            third = items[index + 2]
            first_type = str(first.get("type") or first.get("item_type") or "").strip()
            second_type = str(second.get("type") or second.get("item_type") or "").strip()
            third_type = str(third.get("type") or third.get("item_type") or "").strip()
            output_matches_second = (
                third_type == "function_call_output"
                and str(third.get("call_id") or "").strip()
                and str(third.get("call_id") or "").strip() == str(second.get("call_id") or "").strip()
            )
            if (
                first_type == "function_call"
                and second_type == "function_call"
                and output_matches_second
                and _commands_match_shell_wrapper(_function_call_command(first), _function_call_command(second))
            ):
                canonical.extend([second, third, first])
                index += 3
                continue
        canonical.append(items[index])
        index += 1
    return canonical


def _response_item_inventory(items: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("type") or item.get("item_type") or "").strip()
        for item in list(items or [])
        if str(item.get("type") or item.get("item_type") or "").strip()
    ]


def _provider_extension_inventory(items: list[dict[str, Any]]) -> list[str]:
    return [
        item_type
        for item_type in _response_item_inventory(items)
        if item_type not in _CANONICAL_RESPONSE_ITEM_TYPES
    ]


def _normalize_protocol_value(value: Any, *, parse_json_strings: bool = False) -> Any:
    if parse_json_strings and isinstance(value, str):
        normalized = value.strip()
        if normalized.startswith("{") or normalized.startswith("["):
            try:
                value = json.loads(normalized)
            except json.JSONDecodeError:
                value = value
    if isinstance(value, dict):
        normalized_dict: dict[str, Any] = {}
        for raw_key, item in sorted(value.items(), key=lambda entry: str(entry[0])):
            key = str(raw_key)
            if key in {"id", "call_id", "provider_item_id"}:
                continue
            if key in _IGNORED_PROTOCOL_METADATA_KEYS:
                continue
            normalized_dict[key] = _normalize_protocol_value(item, parse_json_strings=parse_json_strings)
        return normalized_dict
    if isinstance(value, list):
        return [_normalize_protocol_value(item, parse_json_strings=parse_json_strings) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_function_call_output_value(value: Any) -> Any:
    parsed_value = _normalize_protocol_value(value, parse_json_strings=True)
    if not isinstance(parsed_value, dict):
        return parsed_value
    if not any(
        key in parsed_value
        for key in (
            "aggregated_output",
            "command",
            "exit_code",
            "status",
            "stdout",
            "stderr",
            "function_call_output",
            "error",
        )
    ):
        return parsed_value
    for key in ("aggregated_output", "function_call_output", "stdout", "output", "stderr", "error", "text"):
        if key not in parsed_value:
            continue
        normalized_value = _normalize_protocol_value(parsed_value.get(key))
        if not _is_semantically_empty_protocol_value(normalized_value):
            return normalized_value
    return parsed_value


def _is_semantically_empty_protocol_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _response_item_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        return str(content.get("text") or "").strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or block.get("refusal") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _response_item_protocol_signature(item: dict[str, Any]) -> dict[str, Any]:
    item_type = str(item.get("type") or item.get("item_type") or "").strip()
    signature: dict[str, Any] = {"type": item_type}
    for key, value in sorted(item.items(), key=lambda entry: str(entry[0])):
        if key in {"type", "item_type", "id", "call_id", "provider_item_id"}:
            continue
        if key == "status" and item_type in {"message", "output_message"}:
            continue
        if key == "encrypted_content":
            signature["encrypted_content_present"] = bool(str(value or "").strip())
            continue
        if key == "summary" and item_type == "reasoning":
            # Reasoning summary is provider- and transport-variant metadata; it should
            # not gate protocol parity when final behavior and canonical item shapes match.
            continue
        if key == "content":
            if item_type in {"message", "output_message"}:
                signature["content"] = _normalize_protocol_value(value)
                continue
            if item_type == "reasoning":
                normalized_content = _normalize_protocol_value(value)
                if not _is_semantically_empty_protocol_value(normalized_content):
                    signature["content"] = normalized_content
                continue
            normalized_content = _normalize_protocol_value(value)
            if not _is_semantically_empty_protocol_value(normalized_content):
                signature["content"] = normalized_content
            continue
        if key == "arguments":
            signature[key] = _normalize_protocol_value(value, parse_json_strings=True)
            continue
        if key == "output":
            signature[key] = _canonical_function_call_output_value(value)
            continue
        signature[key] = _normalize_protocol_value(value)
    return signature


def _payload_response_item_signatures(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [_response_item_protocol_signature(item) for item in _payload_response_items(payload)]


def _normalized_tool_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, Any] = {}
    command = str(payload.get("command") or payload.get("cmd") or "").strip()
    if not command:
        arguments = payload.get("function_call_arguments")
        if isinstance(arguments, dict):
            command = str(arguments.get("cmd") or arguments.get("command") or "").strip()
    if command:
        normalized["command"] = command
    return normalized


def _tool_event_records(events: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in list(events or []):
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {
            "name": str(item.get("name") or "").strip(),
            "ok": bool(item.get("ok")),
        }
        payload = _normalized_tool_payload(item.get("payload"))
        if payload:
            record["payload"] = payload
        records.append(record)
    return records


def _payload_tool_event_records(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _tool_event_records(list((payload or {}).get("tool_events") or []))


def _command_event_records(turn_events: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in list(turn_events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "command_execution":
            continue
        records.append(
            {
                "event_type": str(event.get("type") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "command": str(item.get("command") or ""),
                "exit_code": item.get("exit_code"),
                "aggregated_output": str(item.get("aggregated_output") or ""),
            }
        )
    return records


def _payload_command_event_records(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _command_event_records(list((payload or {}).get("turn_events") or []))
