from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult, ProviderToolCall
from cli.agent_cli.models import default_response_items
from cli.agent_cli.providers.token_usage_runtime import usage_from_provider_response


def content_text(content: Any, *, content_block_dict_fn: Callable[[Any], dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in list(content or []):
        payload = content_block_dict_fn(block)
        if str(payload.get("type") or "").strip() != "text":
            continue
        text = str(payload.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def server_tool_names(
    content: Any, *, content_block_dict_fn: Callable[[Any], dict[str, Any]]
) -> list[str]:
    names: list[str] = []
    for block in list(content or []):
        payload = content_block_dict_fn(block)
        if str(payload.get("type") or "").strip() != "server_tool_use":
            continue
        name = str(payload.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def assistant_message(
    content: Any, *, content_block_dict_fn: Callable[[Any], dict[str, Any]]
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for block in list(content or []):
        payload = content_block_dict_fn(block)
        block_type = str(payload.get("type") or "").strip()
        if block_type == "text" and str(payload.get("text") or "").strip():
            block_payload = {"type": "text", "text": str(payload.get("text") or "")}
            if isinstance(payload.get("citations"), list):
                block_payload["citations"] = list(payload.get("citations") or [])
            normalized.append(block_payload)
        elif block_type == "tool_use":
            normalized.append(
                {
                    "type": "tool_use",
                    "id": str(payload.get("id") or ""),
                    "name": str(payload.get("name") or ""),
                    "input": payload.get("input") if isinstance(payload.get("input"), dict) else {},
                }
            )
        elif block_type == "server_tool_use":
            normalized.append(
                {
                    "type": "server_tool_use",
                    "id": str(payload.get("id") or ""),
                    "name": str(payload.get("name") or ""),
                    "input": payload.get("input") if isinstance(payload.get("input"), dict) else {},
                    **(
                        {"caller": payload.get("caller")}
                        if payload.get("caller") is not None
                        else {}
                    ),
                }
            )
        elif block_type in {"web_search_tool_result", "web_fetch_tool_result", "tool_result"}:
            block_payload = {
                "type": block_type,
                "tool_use_id": str(payload.get("tool_use_id") or ""),
            }
            if "content" in payload:
                block_payload["content"] = payload.get("content")
            if payload.get("caller") is not None:
                block_payload["caller"] = payload.get("caller")
            if payload.get("is_error") is not None:
                block_payload["is_error"] = bool(payload.get("is_error"))
            normalized.append(block_payload)
    return {"role": "assistant", "content": normalized}


def tool_calls(
    content: Any, *, content_block_dict_fn: Callable[[Any], dict[str, Any]]
) -> list[ProviderToolCall]:
    calls: list[ProviderToolCall] = []
    for block in list(content or []):
        payload = content_block_dict_fn(block)
        if str(payload.get("type") or "").strip() != "tool_use":
            continue
        call_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip()
        arguments = payload.get("input")
        if not call_id or not name or not isinstance(arguments, dict):
            continue
        calls.append(
            ProviderToolCall(
                call_id=call_id,
                name=name,
                arguments=dict(arguments),
                item_type="tool_use",
                raw_item=dict(payload),
            )
        )
    return calls


def build_session_result(
    *,
    response: Any,
    response_content: list[Any],
    response_count: int,
    content_text_fn: Callable[[Any], str],
    tool_calls_fn: Callable[[Any], list[ProviderToolCall]],
    assistant_message_fn: Callable[[Any], dict[str, Any]],
    content_block_dict_fn: Callable[[Any], dict[str, Any]],
    extra_trace: dict[str, Any] | None = None,
) -> tuple[ProviderSessionResult, dict[str, Any]]:
    output_text = content_text_fn(response_content)
    parsed_tool_calls = tool_calls_fn(response_content)
    normalized_assistant_message = assistant_message_fn(response_content)
    native_server_tools = server_tool_names(
        response_content,
        content_block_dict_fn=content_block_dict_fn,
    )
    usage = usage_from_provider_response(response)
    trace = {
        "tool_calls": [call.name for call in parsed_tool_calls],
        "tool_call_count": len(parsed_tool_calls),
        "server_tool_uses": native_server_tools,
        "server_tool_use_count": len(native_server_tools),
        "answered": bool(not parsed_tool_calls and output_text),
        "answer_preview": output_text[:120] if not parsed_tool_calls and output_text else "",
    }
    if usage:
        trace["usage"] = usage
    if isinstance(extra_trace, dict):
        trace.update(dict(extra_trace))
    response_items = default_response_items(
        commentary_text=output_text if parsed_tool_calls else "",
        assistant_text="" if parsed_tool_calls else output_text,
    )
    return (
        ProviderSessionResult(
            output_text=output_text,
            tool_calls=parsed_tool_calls,
            response_items=response_items,
            raw_response=response,
            response_id=str(getattr(response, "id", "") or f"anthropic-{response_count}"),
            trace=trace,
        ),
        normalized_assistant_message,
    )


__all__ = [
    "assistant_message",
    "build_session_result",
    "content_text",
    "server_tool_names",
    "tool_calls",
]
