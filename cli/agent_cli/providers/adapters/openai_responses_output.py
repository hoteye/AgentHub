from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.core.provider_session import ProviderToolCall
from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.providers.adapters import openai_responses_output_runtime as openai_responses_output_runtime_helpers


def _response_field(value: Any, key: str) -> Any:
    return openai_responses_output_runtime_helpers.response_field(value, key)


def _response_content_text(content: Any) -> str:
    return openai_responses_output_runtime_helpers.response_content_text(content)


def _json_ready(value: Any) -> Any:
    return openai_responses_output_runtime_helpers.json_ready(value)


def _response_content_item_to_dict(item: Any) -> Dict[str, Any]:
    return openai_responses_output_runtime_helpers.response_content_item_to_dict(item)


def _response_message_content(content: Any) -> Any:
    return openai_responses_output_runtime_helpers.response_message_content(content)


def _response_reasoning_content(item: Any) -> List[Dict[str, Any]]:
    return openai_responses_output_runtime_helpers.response_reasoning_content(item)


def _response_output_payload_to_response_input_item(payload: Dict[str, Any]) -> ResponseInputItem | None:
    item_type = str(payload.get("type") or "").strip()
    if item_type in {"message", "output_message"}:
        normalized = dict(payload)
        normalized["type"] = "message"
        return ResponseInputItem.from_dict(normalized)
    if item_type == "reasoning":
        return ResponseInputItem.from_dict(payload)
    if not item_type:
        return None
    return ResponseInputItem.from_dict(payload)


def _response_output_payload_to_followup_item(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    item_type = str(payload.get("type") or "").strip()
    if item_type == "output_message":
        normalized = dict(payload)
        normalized["type"] = "message"
        return normalized
    if item_type:
        return dict(payload)
    return None


def _stream_item_to_dict(item: Any) -> Dict[str, Any]:
    return openai_responses_output_runtime_helpers.stream_item_to_dict(item)


def extract_responses_output_items(response: Any) -> List[ResponseInputItem]:
    items: List[ResponseInputItem] = []
    for raw_item in list(getattr(response, "output", []) or []):
        payload = _stream_item_to_dict(raw_item)
        response_item = _response_output_payload_to_response_input_item(payload)
        if response_item is not None:
            items.append(response_item)
    return items


def extract_responses_message_items(response: Any) -> List[ResponseInputItem]:
    return extract_responses_output_items(response)


def extract_responses_output_text(response: Any) -> str:
    direct_text = str(getattr(response, "output_text", "") or "").strip()
    if direct_text:
        return direct_text
    return openai_responses_output_runtime_helpers.extract_output_text_items(list(getattr(response, "output", []) or []))


def _response_output_item_as_input_item(item: Any) -> Dict[str, Any] | None:
    payload = _stream_item_to_dict(item)
    if not payload:
        return None
    return _response_output_payload_to_followup_item(payload)


def extract_responses_followup_items(response: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw_item in list(getattr(response, "output", []) or []):
        payload = _response_output_item_as_input_item(raw_item)
        if payload:
            items.append(payload)
    return items


def _shell_tool_arguments(payload: Dict[str, Any]) -> Dict[str, Any]:
    return openai_responses_output_runtime_helpers.shell_tool_arguments(payload)


def _provider_tool_call_from_payload(payload: Dict[str, Any]) -> ProviderToolCall | None:
    return openai_responses_output_runtime_helpers.provider_tool_call_from_payload(payload)


def _summarize_output_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    return openai_responses_output_runtime_helpers.summarize_output_item(payload)


def _summarize_response_output(response: Any) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for item in list(getattr(response, "output", []) or []):
        payload = _stream_item_to_dict(item)
        if payload:
            summaries.append(_summarize_output_item(payload))
    return summaries
