from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.providers.adapters.openai_responses_output import (
    extract_responses_followup_items,
    extract_responses_output_items,
)
from cli.agent_cli.providers.token_usage_runtime import usage_from_provider_response


_PROVIDER_NATIVE_CONTINUATION_ITEM_TYPES = {"web_search_call"}
_PROVIDER_TOOL_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "shell_call",
    "local_shell_call",
}


def provider_native_continuation_trace(
    *,
    response: Any,
    response_items: List[Any],
    output_text: str,
) -> Dict[str, Any]:
    raw_output = list(getattr(response, "output", []) or [])
    raw_item_types = {
        str(getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else "") or "").strip()
        for item in raw_output
    }
    response_item_types = {
        str(getattr(item, "item_type", "") or "").strip()
        for item in list(response_items or [])
    }
    provider_native_item_types = sorted(
        item_type
        for item_type in raw_item_types.union(response_item_types)
        if item_type in _PROVIDER_NATIVE_CONTINUATION_ITEM_TYPES
    )
    response_status = str(getattr(response, "status", "") or "").strip().lower()
    has_final_message = False
    for item in list(response_items or []):
        item_type = str(getattr(item, "item_type", "") or "").strip()
        if item_type != "message":
            continue
        phase = str(getattr(item, "extra", {}).get("phase") or "").strip().lower()
        if phase == "final_answer":
            has_final_message = True
            break
    has_visible_output = bool(str(output_text or "").strip()) or has_final_message
    if not response_status and response is None and provider_native_item_types:
        response_status = "interrupted"
    pending_native_item = bool(provider_native_item_types) and (
        response_status == "incomplete"
        or response_status == "interrupted"
        or (not has_visible_output)
    )
    search_dispatched = bool(provider_native_item_types)
    search_results_received = bool(provider_native_item_types) and not pending_native_item and has_visible_output
    provider_native_interrupted = search_dispatched and not search_results_received
    search_phase = ""
    if search_dispatched:
        search_phase = "search_results_received" if search_results_received else "search_dispatched"
    provider_native_outcome = ""
    provider_native_error_code = ""
    provider_native_retryable = False
    if search_results_received:
        provider_native_outcome = "search_results_received"
    elif provider_native_interrupted:
        provider_native_outcome = "native_interrupted"
        provider_native_error_code = "native_item_incomplete"
        provider_native_retryable = response_status in {"incomplete", "interrupted"}
    return {
        "provider_native_item_types": provider_native_item_types,
        "provider_native_item_count": len(provider_native_item_types),
        "provider_native_continuation_pending": pending_native_item,
        "provider_native_continuation_reason": "native_item_incomplete" if pending_native_item else "",
        "response_status": response_status,
        "has_final_message": has_final_message,
        "provider_native_search_dispatched": search_dispatched,
        "provider_native_search_results_received": search_results_received,
        "provider_native_search_phase": search_phase,
        "provider_native_interrupted": provider_native_interrupted,
        "provider_native_outcome": provider_native_outcome,
        "provider_native_retryable": provider_native_retryable,
        "provider_native_error_code": provider_native_error_code,
    }


def has_provider_tool_response_items(response_items: List[Any]) -> bool:
    for item in list(response_items or []):
        item_type = str(getattr(item, "item_type", "") or "").strip().lower()
        if item_type in _PROVIDER_TOOL_ITEM_TYPES:
            return True
    return False


def build_response_result(
    session: Any,
    *,
    response: Any,
    normalized_input: List[Dict[str, Any]],
) -> ProviderSessionResult:
    tool_calls = session._response_function_calls(response)
    output_text = session._response_output_text(response)
    response_items = extract_responses_output_items(response)
    followup_items = extract_responses_followup_items(response)
    native_trace = provider_native_continuation_trace(
        response=response,
        response_items=response_items,
        output_text=output_text,
    )
    usage = usage_from_provider_response(response)
    answered = bool(
        not tool_calls
        and not has_provider_tool_response_items(response_items)
        and not native_trace["provider_native_continuation_pending"]
        and (output_text or response_items)
    )
    return ProviderSessionResult(
        output_text=output_text,
        tool_calls=tool_calls,
        response_items=response_items,
        continuation_input_items=[*normalized_input, *followup_items],
        raw_response=response,
        response_id=str(getattr(response, "id", "") or "").strip(),
        trace={
            "tool_calls": [call.name for call in tool_calls],
            "tool_call_count": len(tool_calls),
            "answered": answered,
            "answer_preview": output_text[:120] if answered and output_text else "",
            **({"usage": usage} if usage else {}),
            **native_trace,
        },
    )
