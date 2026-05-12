from __future__ import annotations

import json
from typing import Any, Callable

from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service
from cli.agent_cli.models import FunctionCallOutputPayload, ResponseInputItem
from cli.agent_cli.media_content_runtime import (
    image_content_items_from_output,
    input_image_item_from_image_block,
)


def normalize_input_items(
    input_items: list[dict[str, Any]],
    *,
    reference_parity: bool,
    normalize_single_input_item_fn: Callable[[dict[str, Any], bool], dict[str, Any] | None],
    is_workspace_context_message_fn: Callable[[dict[str, Any]], bool],
    is_environment_context_message_fn: Callable[[dict[str, Any]], bool],
    reference_environment_context_message_fn: Callable[[dict[str, Any]], dict[str, Any]],
    merge_user_message_blocks_fn: Callable[[dict[str, Any], dict[str, Any]], None],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in list(input_items or []):
        if not isinstance(raw, dict):
            continue
        normalized_item = normalize_single_input_item_fn(raw, reference_parity)
        if not normalized_item:
            continue
        if reference_parity and is_environment_context_message_fn(normalized_item):
            normalized_item = reference_environment_context_message_fn(normalized_item)
        if (
            reference_parity
            and normalized
            and is_environment_context_message_fn(normalized_item)
            and is_workspace_context_message_fn(normalized[-1])
        ):
            merge_user_message_blocks_fn(normalized[-1], normalized_item)
            continue
        normalized.append(normalized_item)
    return normalized


def normalize_single_input_item(
    raw: dict[str, Any],
    *,
    reference_parity: bool,
    typed_message_input_item_fn: Callable[[str, Any], dict[str, Any] | None],
    workspace_context_message_text_fn: Callable[[dict[str, Any], bool], str],
) -> dict[str, Any] | None:
    item_type = str(raw.get("type") or "").strip()
    if item_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
        return _normalize_tool_call_item(raw, item_type=item_type)
    if item_type == "reasoning":
        return _normalize_reasoning_item(raw)
    if item_type and item_type not in {
        "response_item",
        "reference_context_item",
        "function_call_output",
        "custom_tool_call_output",
        "message",
    }:
        return ResponseInputItem.from_dict(raw).to_dict()
    if item_type == "response_item":
        return _normalize_response_item(raw, typed_message_input_item_fn=typed_message_input_item_fn)
    if item_type == "reference_context_item":
        return _normalize_reference_context_item(
            raw,
            reference_parity=reference_parity,
            workspace_context_message_text_fn=workspace_context_message_text_fn,
        )
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        return _normalize_function_call_output_item(raw, item_type=item_type)
    if item_type == "message":
        return _normalize_message_item(raw, typed_message_input_item_fn=typed_message_input_item_fn)
    return _normalize_legacy_input_item(raw, typed_message_input_item_fn=typed_message_input_item_fn)


def _normalize_response_item(
    raw: dict[str, Any],
    *,
    typed_message_input_item_fn: Callable[[str, Any], dict[str, Any] | None],
) -> dict[str, Any] | None:
    nested = raw.get("item")
    if not isinstance(nested, dict):
        return None
    normalized_item = ResponseInputItem.from_dict(nested).to_dict()
    nested_type = str(normalized_item.get("type") or "").strip()
    if nested_type == "message":
        return _normalize_message_item(
            normalized_item,
            typed_message_input_item_fn=typed_message_input_item_fn,
        )
    if nested_type == "reasoning":
        return _normalize_reasoning_item(normalized_item)
    if nested_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
        return _normalize_tool_call_item(normalized_item, item_type=nested_type)
    if nested_type in {"function_call_output", "custom_tool_call_output"}:
        return _normalize_function_call_output_item(normalized_item, item_type=nested_type)
    if nested_type:
        return normalized_item
    role = str(normalized_item.get("role") or "").strip()
    content = normalized_item.get("content")
    if role and content:
        return typed_message_input_item_fn(role, content)
    return normalized_item


def _normalize_reference_context_item(
    raw: dict[str, Any],
    *,
    reference_parity: bool,
    workspace_context_message_text_fn: Callable[[dict[str, Any], bool], str],
) -> dict[str, Any] | None:
    payload = raw.get("item")
    if not isinstance(payload, dict):
        return None
    rendered = workspace_context_message_text_fn(payload, reference_parity)
    if not rendered:
        return None
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": rendered}],
    }


def _normalize_function_call_output_item(raw: dict[str, Any], *, item_type: str) -> dict[str, Any] | None:
    call_id = str(raw.get("call_id") or raw.get("tool_call_id") or "").strip()
    if not call_id:
        return None
    output = raw.get("output")
    if output is None:
        output = raw.get("content")
    projected_output = _project_document_output(output)
    if projected_output is None:
        projected_output = _project_image_artifact_output(output)
    if projected_output is not None:
        output = projected_output
    payload = FunctionCallOutputPayload.from_output(output, success=raw.get("success"))
    return {
        "type": item_type,
        "call_id": call_id,
        "output": payload.wire_value(),
    }


def _normalize_message_item(
    raw: dict[str, Any],
    *,
    typed_message_input_item_fn: Callable[[str, Any], dict[str, Any] | None],
) -> dict[str, Any]:
    normalized = ResponseInputItem.from_dict(raw).to_dict()
    if str(normalized.get("type") or "").strip() != "message":
        return normalized
    content = normalized.get("content")
    if not isinstance(content, list):
        role = str(normalized.get("role") or "").strip()
        if role and content is not None:
            typed = typed_message_input_item_fn(role, content)
            if typed is not None:
                typed.update(
                    {
                        key: value
                        for key, value in normalized.items()
                        if key not in {"type", "role", "content"}
                    }
                )
                normalized = typed
                content = normalized.get("content")
    if not isinstance(content, list):
        return normalized
    normalized_blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        normalized_block = _normalize_message_content_block(block)
        if normalized_block is not None:
            normalized_blocks.append(normalized_block)
    if normalized_blocks:
        normalized["content"] = normalized_blocks
    return normalized


def _normalize_reasoning_item(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = ResponseInputItem.from_dict(raw).to_dict()
    if str(normalized.get("type") or "").strip() != "reasoning":
        return normalized
    if str(normalized.get("encrypted_content") or "").strip() and normalized.get("summary") in (None, ""):
        normalized["summary"] = []
    return normalized


def _normalize_legacy_input_item(
    raw: dict[str, Any],
    *,
    typed_message_input_item_fn: Callable[[str, Any], dict[str, Any] | None],
) -> dict[str, Any] | None:
    role = str(raw.get("role") or "").strip().lower()
    if role == "tool":
        call_id = str(raw.get("tool_call_id") or raw.get("call_id") or "").strip()
        if not call_id:
            return None
        output = raw.get("content")
        if output is None:
            output = raw.get("output")
        projected_output = _project_document_output(output)
        if projected_output is None:
            projected_output = _project_image_artifact_output(output)
        if projected_output is not None:
            output = projected_output
        payload = FunctionCallOutputPayload.from_output(output, success=raw.get("success"))
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": payload.wire_value(),
        }
    if "role" in raw and "content" in raw and not str(raw.get("type") or "").strip():
        message_role = str(raw.get("role") or "user").strip() or "user"
        return typed_message_input_item_fn(message_role, raw.get("content"))
    return dict(raw)


def _input_image_item_from_provider_image_block(payload: dict[str, Any]) -> dict[str, Any] | None:
    return input_image_item_from_image_block(payload)


def _project_document_output(output: Any) -> Any:
    projection = models_mapping_runtime_service.view_document_output_projection(output)
    if projection is None:
        return None
    return projection.get("output")


def _project_image_artifact_output(output: Any) -> list[dict[str, Any]] | None:
    return image_content_items_from_output(
        output,
        image_item_normalizer=_input_image_item_from_provider_image_block,
    )


def _normalize_message_content_block(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = str(block.get("type") or "").strip().lower()
    if block_type in {"input_image", "image"}:
        normalized = _input_image_item_from_provider_image_block(block)
        if normalized is not None:
            return normalized
        return dict(block)
    return dict(block)


def _normalize_tool_call_string_value(value: Any, *, empty_fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        return text if text else empty_fallback
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except TypeError:
        return empty_fallback


def _should_preserve_provider_tool_item_id(item_id: Any, *, call_id: str) -> bool:
    normalized = str(item_id or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return False
    if normalized == call_id:
        return False
    if lowered == "item" or lowered.startswith(("item_", "item-", "item.", "stream_item_")):
        return False
    return True


def _normalize_tool_call_item(raw: dict[str, Any], *, item_type: str) -> dict[str, Any] | None:
    if item_type == "function_call":
        call_id = str(raw.get("call_id") or raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not (call_id and name):
            return None
        status = str(raw.get("status") or "").strip()
        normalized = {
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": _normalize_tool_call_string_value(
                raw.get("arguments"),
                empty_fallback="" if status.lower() in {"in_progress", "incomplete"} else "{}",
            ),
        }
        provider_item_id = raw.get("id")
        if _should_preserve_provider_tool_item_id(provider_item_id, call_id=call_id):
            normalized["id"] = str(provider_item_id).strip()
        namespace = raw.get("namespace")
        if namespace not in (None, ""):
            normalized["namespace"] = namespace
        if status:
            normalized["status"] = status
        return normalized
    if item_type == "custom_tool_call":
        call_id = str(raw.get("call_id") or raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not (call_id and name):
            return None
        status = str(raw.get("status") or "").strip()
        normalized = {
            "type": "custom_tool_call",
            "call_id": call_id,
            "name": name,
            "input": _normalize_tool_call_string_value(
                raw.get("input"),
                empty_fallback="" if status.lower() in {"in_progress", "incomplete"} else "",
            ),
        }
        provider_item_id = raw.get("id")
        if _should_preserve_provider_tool_item_id(provider_item_id, call_id=call_id):
            normalized["id"] = str(provider_item_id).strip()
        namespace = raw.get("namespace")
        if namespace not in (None, ""):
            normalized["namespace"] = namespace
        if status:
            normalized["status"] = status
        return normalized
    call_id = str(raw.get("call_id") or raw.get("id") or "").strip()
    if not call_id:
        return None
    action = raw.get("action")
    if not isinstance(action, dict):
        return None
    normalized = {
        "type": item_type,
        "call_id": call_id,
        "action": dict(action),
    }
    provider_item_id = raw.get("id")
    if _should_preserve_provider_tool_item_id(provider_item_id, call_id=call_id):
        normalized["id"] = str(provider_item_id).strip()
    created_by = raw.get("created_by")
    if created_by not in (None, ""):
        normalized["created_by"] = created_by
    environment = raw.get("environment")
    if environment is not None:
        normalized["environment"] = dict(environment) if isinstance(environment, dict) else environment
    status = str(raw.get("status") or "").strip()
    if status:
        normalized["status"] = status
    return normalized
