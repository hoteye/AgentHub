from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.core.provider_session_tool_results_runtime import default_tool_result_items
from cli.agent_cli.models import AgentIntent, ToolEvent, function_call_input_items_from_turn_events
from cli.agent_cli.runtime_services.approval_continuation_runtime_record_helpers_runtime import (
    _dict,
    _list_of_dicts,
)

_PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS = (
    "unsupported parameter",
    "unsupported_parameter",
    "unknown parameter",
    "unexpected parameter",
    "unrecognized parameter",
)
_GENERIC_CHAT_PLANNER_KINDS = {
    "openai_chat",
    "deepseek_chat",
    "deepseek_reasoner",
}
_GENERIC_CHAT_WIRE_APIS = {
    "openai_chat",
    "deepseek_chat",
}
_TOOL_CALL_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "local_shell_call",
    "shell_call",
}
_TOOL_OUTPUT_ITEM_TYPES = {
    "function_call_output",
    "custom_tool_call_output",
    "local_shell_call_output",
    "shell_call_output",
}


def _text_mentions_previous_response_id_unsupported(value: Any) -> bool:
    lowered = str(value or "").strip().lower()
    if "previous_response_id" not in lowered:
        return False
    return any(marker in lowered for marker in _PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS)


def _intent_mentions_previous_response_id_unsupported(intent: Any) -> bool:
    if _text_mentions_previous_response_id_unsupported(getattr(intent, "assistant_text", "")):
        return True
    if _text_mentions_previous_response_id_unsupported(getattr(intent, "commentary_text", "")):
        return True
    diagnostics = _dict(getattr(intent, "protocol_diagnostics", None))
    for key in ("provider_runtime_error", "error", "last_error"):
        if _text_mentions_previous_response_id_unsupported(diagnostics.get(key)):
            return True
    for value in list(diagnostics.get("provider_runtime_error_diagnostics") or []):
        if _text_mentions_previous_response_id_unsupported(value):
            return True
    return False


def _intent_is_degraded_provider_failure(intent: Any) -> bool:
    if str(getattr(intent, "status_hint", "") or "").strip().lower() == "degraded":
        return True
    diagnostics = _dict(getattr(intent, "protocol_diagnostics", None))
    protocol_path = _dict(diagnostics.get("protocol_path"))
    return str(protocol_path.get("kind") or "").strip() == "provider_degraded_fallback"


def _runtime_provider_field(runtime: Any, key: str) -> str:
    agent = getattr(runtime, "agent", None)
    status_getter = getattr(agent, "provider_status", None)
    if callable(status_getter):
        try:
            status = dict(status_getter() or {})
        except Exception:
            status = {}
        value = str(status.get(key) or "").strip()
        if value:
            return value
    planner = getattr(agent, "_planner", None) or agent
    config = getattr(planner, "config", None)
    if config is not None:
        if key == "provider_planner":
            return str(getattr(config, "planner_kind", "") or "").strip()
        if key == "wire_api":
            return str(getattr(config, "wire_api", "") or "").strip()
        if key == "provider_name":
            return str(getattr(config, "provider_name", "") or "").strip()
    return ""


def _runtime_uses_generic_chat_continuation(
    runtime: Any, continuation_result: dict[str, Any]
) -> bool:
    provider_session_kind = (
        str(continuation_result.get("provider_session_kind") or "").strip().lower()
    )
    if (
        provider_session_kind in _GENERIC_CHAT_PLANNER_KINDS
        or provider_session_kind in _GENERIC_CHAT_WIRE_APIS
    ):
        return True
    planner_kind = _runtime_provider_field(runtime, "provider_planner").strip().lower()
    wire_api = _runtime_provider_field(runtime, "wire_api").strip().lower()
    provider_name = _runtime_provider_field(runtime, "provider_name").strip().lower()
    if planner_kind in _GENERIC_CHAT_PLANNER_KINDS or wire_api in _GENERIC_CHAT_WIRE_APIS:
        return True
    return provider_name in {"deepseek", "glm"} and planner_kind not in {
        "anthropic_messages",
        "openai_responses",
    }


def _degraded_generic_chat_intent(continuation_result: dict[str, Any]) -> AgentIntent:
    output_preview = ""
    for item in _list_of_dicts(continuation_result.get("tool_output_items")):
        output = item.get("output")
        if output is not None:
            output_preview = str(output or "").strip()
            break
    if len(output_preview) > 800:
        output_preview = f"{output_preview[:797]}..."
    if not output_preview:
        output_preview = (
            "Approval decision was recorded, but no provider-readable tool output was available."
        )
    message = (
        "审批动作已处理，但当前 provider 使用 generic chat-completions 工具协议，"
        "无法安全还原原生 tool-call -> tool-result 续跑链路；已按 degraded continuation 处理。\n"
        f"工具结果：{output_preview}"
    )
    continuation_result["continuation_attempted"] = True
    continuation_result["continuation_status"] = "degraded"
    continuation_result["degraded_reason"] = "generic_chat_continuation_not_native"
    continuation_result["assistant_text"] = message
    return AgentIntent(
        assistant_text=message,
        status_hint="degraded",
        protocol_diagnostics={
            "approval_continuation": {
                "status": "degraded",
                "reason": "generic_chat_continuation_not_native",
            }
        },
    )


def _serialized_arguments(arguments: Any) -> str:
    try:
        return json.dumps(arguments if isinstance(arguments, dict) else {}, ensure_ascii=False)
    except TypeError:
        return "{}"


def _item_call_id(item: dict[str, Any]) -> str:
    return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()


def _nested_response_item(item: dict[str, Any]) -> dict[str, Any]:
    if str(item.get("type") or "").strip() != "response_item":
        return {}
    return _dict(item.get("item"))


def _tool_call_ids(items: list[dict[str, Any]]) -> set[str]:
    call_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = _nested_response_item(item)
        candidate = nested if nested else item
        if str(candidate.get("type") or "").strip() not in _TOOL_CALL_ITEM_TYPES:
            continue
        call_id = _item_call_id(candidate)
        if call_id:
            call_ids.add(call_id)
    return call_ids


def _tool_output_call_id(item: dict[str, Any]) -> str:
    nested = _nested_response_item(item)
    candidate = nested if nested else item
    if str(candidate.get("type") or "").strip() not in _TOOL_OUTPUT_ITEM_TYPES:
        return ""
    return _item_call_id(candidate)


def replay_items_without_orphan_tool_outputs(
    replay_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    paired_call_ids = _tool_call_ids(replay_items)
    filtered: list[dict[str, Any]] = []
    stripped_call_ids: list[str] = []
    for item in replay_items:
        if not isinstance(item, dict):
            continue
        output_call_id = _tool_output_call_id(item)
        if output_call_id and output_call_id not in paired_call_ids:
            stripped_call_ids.append(output_call_id)
            continue
        filtered.append(dict(item))
    return filtered, stripped_call_ids


def _direct_tool_call_replay_items_from_provider_context(
    continuation: dict[str, Any],
) -> list[dict[str, Any]]:
    call_id = str(continuation.get("provider_call_id") or "").strip()
    if not call_id:
        return []
    raw_item = _dict(continuation.get("provider_raw_item"))
    provider_tool_type = str(continuation.get("provider_tool_type") or "").strip().lower()
    raw_type = str(raw_item.get("type") or provider_tool_type or "").strip().lower()
    name = str(raw_item.get("name") or continuation.get("function_call_name") or "").strip()
    if not name:
        return []
    function_arguments = _dict(continuation.get("function_call_arguments"))
    raw_input = raw_item.get("input")
    arguments = dict(raw_input) if isinstance(raw_input, dict) else function_arguments
    if provider_tool_type == "custom_tool_call" or raw_type == "custom_tool_call":
        raw_input_text = str(raw_item.get("input") or "").strip()
        input_text = (
            raw_input_text or str(arguments.get("patch") or arguments.get("input") or "").strip()
        )
        if not input_text:
            return []
        return [
            {
                "type": "custom_tool_call",
                "call_id": call_id,
                "name": name,
                "input": input_text,
            }
        ]
    if raw_type in {"tool_use", "function_call"} or provider_tool_type in {
        "tool_use",
        "function_call",
    }:
        return [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": _serialized_arguments(arguments),
            }
        ]
    if raw_type in {"local_shell_call", "shell_call"}:
        replay_item = dict(raw_item)
        replay_item["type"] = raw_type
        replay_item["call_id"] = call_id
        return [replay_item]
    return []


def _tool_call_replay_items_from_executed_events(
    continuation: dict[str, Any],
) -> list[dict[str, Any]]:
    call_id = str(continuation.get("provider_call_id") or "").strip()
    if not call_id:
        return []
    candidates = function_call_input_items_from_turn_events(
        _list_of_dicts(continuation.get("executed_item_events_before_approval"))
    )
    return [
        dict(item)
        for item in list(candidates or [])
        if isinstance(item, dict)
        and str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
        == call_id
    ]


def _tool_call_replay_items(continuation: dict[str, Any]) -> list[dict[str, Any]]:
    direct_items = _direct_tool_call_replay_items_from_provider_context(continuation)
    if direct_items:
        return direct_items
    return _tool_call_replay_items_from_executed_events(continuation)


def _action_result_payload(decision_response: dict[str, Any]) -> dict[str, Any]:
    action_result = decision_response.get("action_result")
    to_dict = getattr(action_result, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value) if isinstance(value, dict) else {}
    return _dict(action_result)


def _approved_from_decision_response(decision_response: dict[str, Any]) -> bool:
    ticket = decision_response.get("approval_ticket")
    status = str(getattr(ticket, "status", "") or "").strip().lower()
    return status == "approved"


def _tool_event_for_decision(
    *,
    continuation: dict[str, Any],
    decision_response: dict[str, Any],
) -> ToolEvent:
    approved = _approved_from_decision_response(decision_response)
    action_result = _action_result_payload(decision_response)
    action_output = _dict(action_result.get("output"))
    ok = bool(action_result.get("ok")) if action_result else False
    if not approved:
        ok = False
    output_text = str(
        action_output.get("function_call_output")
        or action_output.get("aggregated_output")
        or action_output.get("stdout")
        or ""
    ).strip()
    if not output_text:
        output_text = str(action_result.get("summary") or "").strip()
    if not output_text and not approved:
        output_text = (
            f"User rejected approval {continuation.get('approval_id')}. "
            "The requested action was not executed."
        )
    if not output_text:
        output_text = "Approval action completed."
    payload = {
        "provider_call_id": str(continuation.get("provider_call_id") or "").strip(),
        "provider_tool_type": str(continuation.get("provider_tool_type") or "").strip(),
        "provider_raw_item": _dict(continuation.get("provider_raw_item")),
        "function_call_name": str(continuation.get("function_call_name") or "").strip(),
        "function_call_arguments": _dict(continuation.get("function_call_arguments")),
        "function_call_output": output_text,
        "function_call_output_model_visible": True,
        "status": "completed" if ok else "failed",
        "stdout": str(action_output.get("stdout") or output_text if ok else ""),
        "stderr": str(action_output.get("stderr") or ""),
        "aggregated_output": output_text,
        "exit_code": 0 if ok else 1,
        "approval_id": str(continuation.get("approval_id") or "").strip(),
        "action_id": str(continuation.get("action_id") or "").strip(),
    }
    return ToolEvent(
        name=str(continuation.get("function_call_name") or "approval_continuation"),
        ok=ok,
        summary=str(action_result.get("summary") or output_text),
        payload=payload,
    )


def build_approval_tool_output_items(
    *,
    continuation: dict[str, Any],
    decision_response: dict[str, Any],
) -> list[dict[str, Any]]:
    call_id = str(continuation.get("provider_call_id") or "").strip()
    if not call_id:
        return []
    event = _tool_event_for_decision(
        continuation=continuation,
        decision_response=decision_response,
    )
    return default_tool_result_items(
        call_id=call_id,
        command_text=str(continuation.get("command_text") or "").strip() or None,
        assistant_text=str(event.payload.get("function_call_output") or event.summary or ""),
        events=[event],
    )
