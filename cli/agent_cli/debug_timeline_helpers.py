from __future__ import annotations

import json
from typing import Any, Callable, Dict, List


def _preview_text(value: Any, *, max_chars: int = 120) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for entry in content:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or entry.get("refusal") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _structured_output_preview(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _preview_text(value)
    if isinstance(value, dict):
        for key in ("aggregated_output", "stdout", "stderr", "text", "output", "content", "result"):
            text = str(value.get(key) or "").strip()
            if text:
                return _preview_text(text)
        return _preview_text(json.dumps(value, ensure_ascii=False))
    if isinstance(value, list):
        parts: List[str] = []
        for entry in value:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(entry, dict):
                continue
            for key in ("stdout", "stderr", "text", "output", "content"):
                text = str(entry.get(key) or "").strip()
                if text:
                    parts.append(text)
                    break
        return _preview_text("\n".join(parts))
    return _preview_text(value)


def _commands_preview(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    commands = action.get("commands")
    if isinstance(commands, list):
        normalized = [str(item).strip() for item in commands if str(item).strip()]
        if normalized:
            return _preview_text(" && ".join(normalized))
    for key in ("command", "query"):
        text = str(action.get(key) or "").strip()
        if text:
            return _preview_text(text)
    return ""


def _is_plain_user_message(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    item_type = str(item.get("type") or item.get("item_type") or "").strip()
    looks_like_message = item_type == "message" or (
        "role" in item and "content" in item and not item_type
    )
    return (
        looks_like_message
        and str(item.get("role") or "").strip().lower() == "user"
    )


def _content_summary(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        text = content.strip()
        return [{"type": "text", "preview": _preview_text(text)}] if text else []
    if not isinstance(content, list):
        return []
    blocks: List[Dict[str, Any]] = []
    for entry in content:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                blocks.append({"type": "text", "preview": _preview_text(text)})
            continue
        if not isinstance(entry, dict):
            continue
        block_type = str(entry.get("type") or "").strip() or "unknown"
        payload: Dict[str, Any] = {"type": block_type}
        if block_type in {"input_text", "output_text", "text", "reasoning"}:
            text = str(entry.get("text") or "").strip()
            if text:
                payload["preview"] = _preview_text(text)
        elif block_type == "input_image":
            image_url = str(entry.get("image_url") or "").strip()
            if image_url:
                payload["image_url"] = _preview_text(image_url)
        blocks.append(payload)
    return blocks


def summarize_input_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {"type": type(item).__name__, "preview": _preview_text(item)}
    item_type = str(item.get("type") or item.get("item_type") or "").strip() or "message"
    if item_type == "message":
        summary = {
            "type": "message",
            "role": str(item.get("role") or "").strip() or None,
            "content": _content_summary(item.get("content")),
        }
        phase = str(item.get("phase") or "").strip()
        if phase:
            summary["phase"] = phase
        return summary
    if item_type == "reasoning":
        summary = {
            "type": "reasoning",
            "status": item.get("status"),
            "preview": _preview_text(_content_text(item.get("content"))),
        }
        provider_item_id = str(item.get("id") or "").strip()
        if provider_item_id:
            summary["provider_item_id"] = provider_item_id
        reasoning_summary = item.get("summary")
        if reasoning_summary not in (None, "", []):
            summary["summary_preview"] = _preview_text(reasoning_summary, max_chars=160)
        if item.get("encrypted_content") not in (None, ""):
            summary["encrypted_content_present"] = True
        return summary
    if item_type in {"function_call", "custom_tool_call"}:
        summary = {
            "type": item_type,
            "name": str(item.get("name") or "").strip() or None,
            "call_id": str(item.get("call_id") or "").strip() or None,
            "arguments_preview": _preview_text(item.get("arguments") if item_type == "function_call" else item.get("input")),
        }
        if "status" in item:
            summary["status"] = item.get("status")
        provider_item_id = str(item.get("id") or "").strip()
        if provider_item_id:
            summary["provider_item_id"] = provider_item_id
        return summary
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        return {
            "type": item_type,
            "call_id": str(item.get("call_id") or item.get("tool_call_id") or "").strip() or None,
            "success": item.get("success"),
            "preview": _structured_output_preview(
                item.get("output") if item.get("output") is not None else item.get("content")
            ),
        }
    if item_type in {"shell_call", "local_shell_call"}:
        summary = {
            "type": item_type,
            "call_id": str(item.get("call_id") or "").strip() or None,
            "status": item.get("status"),
        }
        provider_item_id = str(item.get("id") or "").strip()
        if provider_item_id:
            summary["provider_item_id"] = provider_item_id
        command_preview = _commands_preview(item.get("action"))
        if command_preview:
            summary["command_preview"] = command_preview
        return summary
    if item_type in {"shell_call_output", "local_shell_call_output"}:
        summary = {
            "type": item_type,
            "call_id": str(item.get("call_id") or "").strip() or None,
            "status": item.get("status"),
        }
        output_preview = _structured_output_preview(item.get("output"))
        if output_preview:
            summary["output_preview"] = output_preview
        return summary
    if item_type == "web_search_call":
        summary = {
            "type": "web_search_call",
            "status": item.get("status"),
        }
        provider_item_id = str(item.get("id") or "").strip()
        if provider_item_id:
            summary["provider_item_id"] = provider_item_id
        call_id = str(item.get("call_id") or "").strip()
        if call_id:
            summary["call_id"] = call_id
        query_preview = _commands_preview(item.get("action")) or _preview_text(item.get("query"))
        if query_preview:
            summary["query_preview"] = query_preview
        return summary
    if item_type == "response_item":
        nested = item.get("item")
        summary = summarize_input_item(nested)
        summary["wrapper_type"] = "response_item"
        return summary
    if item_type in {"reference_context_item", "state_snapshot"}:
        nested = item.get("item")
        return {
            "type": item_type,
            "preview": _preview_text(nested if nested is not None else item),
        }
    summary = {"type": item_type}
    if "role" in item:
        summary["role"] = str(item.get("role") or "").strip() or None
    if "content" in item:
        summary["content"] = _content_summary(item.get("content"))
    if "call_id" in item:
        summary["call_id"] = str(item.get("call_id") or "").strip() or None
    if "name" in item:
        summary["name"] = str(item.get("name") or "").strip() or None
    if "status" in item:
        summary["status"] = item.get("status")
    return summary


def summarize_input_items_tail(items: List[Any] | None, *, tail_len: int = 8) -> List[Dict[str, Any]]:
    normalized = list(items or [])
    if tail_len <= 0:
        return []
    tail = normalized[-tail_len:]
    return [summarize_input_item(item) for item in tail]


def summarize_protocol_items_tail(items: List[Any] | None, *, tail_len: int = 8) -> List[Dict[str, Any]]:
    return summarize_input_items_tail(items, tail_len=tail_len)


def summarize_current_turn_driver_tail(
    items: List[Any] | None,
    *,
    tail_len: int = 8,
    extract_current_turn_prelude_items_fn: Callable[[List[Dict[str, Any]]], List[Any]] | None = None,
) -> List[Dict[str, Any]]:
    normalized = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    if tail_len <= 0 or not normalized:
        return []
    end_index = len(normalized)
    if _is_plain_user_message(normalized[-1]):
        end_index -= 1
        prelude_items: List[Any] | None = None
        if extract_current_turn_prelude_items_fn is not None:
            try:
                prelude_items = extract_current_turn_prelude_items_fn(normalized)
            except Exception:
                prelude_items = None
        if prelude_items:
            end_index = max(0, end_index - len(list(prelude_items)))
    conversation_items = normalized[:end_index]
    if not conversation_items:
        return []
    start_index = 0
    for index in range(len(conversation_items) - 1, -1, -1):
        if _is_plain_user_message(conversation_items[index]):
            start_index = index + 1
            break
    driver_items = conversation_items[start_index:] or conversation_items[-tail_len:]
    return [summarize_input_item(item) for item in driver_items[-tail_len:]]
