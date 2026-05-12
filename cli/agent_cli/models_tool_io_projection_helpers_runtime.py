from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.models_tool_io_normalization_helpers_runtime import (
    effective_function_call_name,
    normalized_tool_events,
    tool_event_call_id,
    tool_event_function_call_arguments,
    tool_event_provider_item_type,
    tool_event_provider_raw_item,
)
from cli.agent_cli.models_tool_io_pure_helpers_runtime import (
    shell_action_from_payload,
    tool_event_payload,
)


def _model_symbols() -> tuple[Any, Any, Any]:
    from cli.agent_cli.models import FunctionCallOutputPayload, ResponseInputItem, tool_event_result_text

    return FunctionCallOutputPayload, ResponseInputItem, tool_event_result_text


def normalized_provider_tool_input_item(tool_event: Any) -> dict[str, Any] | None:
    _, response_input_item_model, _ = _model_symbols()
    payload = tool_event_payload(tool_event)
    call_id = tool_event_call_id(tool_event)
    provider_item_type = tool_event_provider_item_type(tool_event)
    raw_item = tool_event_provider_raw_item(tool_event)
    if isinstance(raw_item, dict) and raw_item:
        normalized_raw = response_input_item_model.from_dict(raw_item).to_dict()
        normalized_type = str(normalized_raw.get("type") or "").strip().lower()
        if normalized_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
            if call_id and not str(normalized_raw.get("call_id") or "").strip():
                normalized_raw["call_id"] = call_id
            if normalized_type == "function_call":
                normalized_raw.setdefault(
                    "name",
                    effective_function_call_name(tool_event),
                )
                if normalized_raw.get("arguments") in (None, ""):
                    try:
                        normalized_raw["arguments"] = json.dumps(
                            tool_event_function_call_arguments(tool_event) or {},
                            ensure_ascii=False,
                        )
                    except TypeError:
                        normalized_raw["arguments"] = "{}"
            elif normalized_type == "custom_tool_call":
                normalized_raw.setdefault(
                    "name",
                    effective_function_call_name(tool_event),
                )
                if normalized_raw.get("input") in (None, ""):
                    arguments = tool_event_function_call_arguments(tool_event) or {}
                    normalized_raw["input"] = str(arguments.get("patch") or arguments.get("input") or "").strip()
            else:
                action = dict(normalized_raw.get("action") or {})
                if not action:
                    action = shell_action_from_payload(payload)
                normalized_raw["action"] = action
            status = str(payload.get("status") or "").strip()
            if status and not str(normalized_raw.get("status") or "").strip():
                normalized_raw["status"] = status
            return normalized_raw

    if provider_item_type == "custom_tool_call":
        arguments = tool_event_function_call_arguments(tool_event) or {}
        item = {
            "type": "custom_tool_call",
            "call_id": call_id,
            "name": effective_function_call_name(tool_event),
            "input": str(arguments.get("patch") or arguments.get("input") or "").strip(),
        }
        status = str(payload.get("status") or "").strip()
        if status:
            item["status"] = status
        return item

    if provider_item_type in {"shell_call", "local_shell_call"}:
        item: dict[str, Any] = {
            "type": provider_item_type,
            "call_id": call_id,
            "action": shell_action_from_payload(payload),
        }
        status = str(payload.get("status") or "").strip()
        if status:
            item["status"] = status
        return item
    return None


def shell_output_blocks_from_payload(payload: dict[str, Any], *, ok: bool) -> list[dict[str, Any]]:
    block: dict[str, Any] = {}
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    aggregated_output = payload.get("aggregated_output")
    if stdout is None and stderr is None and aggregated_output is not None:
        stdout = aggregated_output
    if stdout is not None:
        block["stdout"] = str(stdout)
    if stderr is not None:
        block["stderr"] = str(stderr)

    outcome: dict[str, Any] = {}
    if payload.get("timed_out"):
        outcome["type"] = "timeout"
    elif payload.get("interrupted"):
        outcome["type"] = "interrupted"
    else:
        outcome["type"] = "exit"
        exit_code = payload.get("exit_code", payload.get("returncode"))
        if exit_code is None:
            exit_code = 0 if ok else 1
        try:
            outcome["exit_code"] = int(exit_code)
        except (TypeError, ValueError):
            pass
    if outcome:
        block["outcome"] = outcome
    return [block] if block else []


def normalized_provider_tool_output_item(tool_event: Any) -> dict[str, Any] | None:
    function_call_output_payload_model, _, result_text_fn = _model_symbols()
    payload = tool_event_payload(tool_event)
    call_id = tool_event_call_id(tool_event)
    provider_item_type = tool_event_provider_item_type(tool_event)
    if provider_item_type == "custom_tool_call":
        output_payload = payload.get("function_call_output")
        if output_payload is None:
            result_text = result_text_fn(tool_event)
            output_payload = result_text if result_text else str(getattr(tool_event, "summary", "") or "").strip()
        output = function_call_output_payload_model.from_output(output_payload, success=bool(getattr(tool_event, "ok", False)))
        item = {
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": output.wire_value(),
        }
        if output.success is not None:
            item["success"] = output.success
        return item
    if provider_item_type not in {"shell_call", "local_shell_call"}:
        return None
    output_item_type = "local_shell_call_output" if provider_item_type == "local_shell_call" else "shell_call_output"
    item: dict[str, Any] = {
        "type": output_item_type,
        "call_id": call_id,
        "output": shell_output_blocks_from_payload(payload, ok=bool(getattr(tool_event, "ok", False))),
    }
    raw_item = tool_event_provider_raw_item(tool_event)
    action = dict(raw_item.get("action") or {}) if isinstance(raw_item.get("action"), dict) else {}
    max_output_length = raw_item.get("max_output_length", action.get("max_output_length"))
    if max_output_length is None:
        max_output_length = payload.get("max_output_length", payload.get("max_output_chars"))
    if max_output_length is not None:
        item["max_output_length"] = max_output_length
    status = str(payload.get("status") or "").strip()
    if status:
        item["status"] = status
    return item


def function_call_input_items_from_tool_events_projection(tool_events: list[Any] | None) -> list[dict[str, Any]]:
    _, response_input_item_model, _ = _model_symbols()
    items: list[dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for tool_event in normalized_tool_events(tool_events):
        call_id = tool_event_call_id(tool_event)
        if not call_id or call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        provider_item = normalized_provider_tool_input_item(tool_event)
        if provider_item is not None:
            items.append(provider_item)
            continue
        arguments_value = tool_event_function_call_arguments(tool_event)
        try:
            arguments = json.dumps(arguments_value or {}, ensure_ascii=False)
        except TypeError:
            arguments = "{}"
        fallback_item_type = (
            "custom_tool_call"
            if str((getattr(tool_event, "payload", {}) or {}).get("provider_tool_type") or "").strip().lower()
            == "custom_tool_call"
            else "function_call"
        )
        fallback_extra = {
            "name": effective_function_call_name(tool_event),
            "call_id": call_id,
        }
        if fallback_item_type == "custom_tool_call":
            arguments_value = tool_event_function_call_arguments(tool_event) or {}
            fallback_extra["input"] = str(arguments_value.get("patch") or arguments_value.get("input") or "").strip()
        else:
            fallback_extra["arguments"] = arguments
        items.append(
            response_input_item_model(
                item_type=fallback_item_type,
                extra=fallback_extra,
            ).to_dict()
        )
    return items


def tool_output_input_items_from_tool_events_projection(tool_events: list[Any] | None) -> list[dict[str, Any]]:
    function_call_output_payload_model, response_input_item_model, result_text_fn = _model_symbols()
    items: list[dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for tool_event in normalized_tool_events(tool_events):
        call_id = tool_event_call_id(tool_event)
        if not call_id or call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        provider_output_item = normalized_provider_tool_output_item(tool_event)
        if provider_output_item is not None:
            items.append(provider_output_item)
            continue
        payload = tool_event_payload(tool_event)
        explicit_output = payload.get("function_call_output")
        success = bool(getattr(tool_event, "ok", False))
        if explicit_output is not None:
            output_value = explicit_output
        else:
            result_text = result_text_fn(tool_event)
            if result_text:
                output_value = result_text
            elif payload:
                output_value = payload
            else:
                output_value = str(getattr(tool_event, "summary", "") or "").strip()
        output_payload = function_call_output_payload_model.from_output(output_value, success=success)
        output_item_type = (
            "custom_tool_call_output"
            if str((getattr(tool_event, "payload", {}) or {}).get("provider_tool_type") or "").strip().lower()
            == "custom_tool_call"
            else "function_call_output"
        )
        items.append(
            response_input_item_model(
                item_type=output_item_type,
                extra={
                    "call_id": call_id,
                    "output": output_payload.wire_value(),
                    "success": output_payload.success,
                },
            ).to_dict()
        )
    return items


__all__ = [
    "function_call_input_items_from_tool_events_projection",
    "normalized_provider_tool_input_item",
    "normalized_provider_tool_output_item",
    "shell_output_blocks_from_payload",
    "tool_output_input_items_from_tool_events_projection",
]
