from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import PromptAttachment, ToolEvent
from cli.agent_cli.providers.planner_postprocessing import (
    GENERIC_SYNTHESIS_RULES,
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    sanitize_final_answer_text,
    structured_tool_fallback_text,
)


def chat_route_request_kwargs(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    extra_body: Any,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    return kwargs


def chat_route_assistant_text(
    *,
    response: Any,
    chat_message_text: str,
    executed_events: List[ToolEvent],
) -> str:
    assistant_text = sanitize_final_answer_text(chat_message_text or "")
    if assistant_text:
        return assistant_text
    return structured_tool_fallback_text(executed_events) or "模型未返回内容。"


def stream_text_from_events(stream: Any) -> str:
    text_parts: List[str] = []
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type in {"response.output_text.delta", "response.refusal.delta"}:
            delta = getattr(event, "delta", "")
            if delta:
                text_parts.append(str(delta))
    return "".join(text_parts).strip()


def synthesis_user_content(
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachment_payloads: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parts = [
        *GENERIC_SYNTHESIS_RULES,
        "",
        "ORIGINAL_USER_REQUEST:",
        user_text,
        "",
        "TOOL_RESULT_SUMMARY:",
        "\n".join(generic_tool_event_summary_lines(executed_events)) or "- no tool events",
        "",
        "TOOL_RESULT_CONTEXT_JSON:",
        json.dumps(generic_tool_event_context_blocks(executed_events), ensure_ascii=False, indent=2),
    ]
    item_blocks = executed_item_event_context_blocks(executed_item_events or [])
    if item_blocks:
        parts.extend(
            [
                "",
                "EXECUTED_ITEM_EVENTS_JSON:",
                json.dumps(item_blocks, ensure_ascii=False, indent=2),
            ]
        )
    if attachment_payloads:
        parts.extend(
            [
                "",
                "ATTACHMENTS_JSON:",
                json.dumps(attachment_payloads, ensure_ascii=False, indent=2),
            ]
        )
    return "\n".join(parts)


def synthesis_messages(
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    attachment_payloads_fn: Any,
) -> List[Dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": synthesis_user_content(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
                attachment_payloads=attachment_payloads_fn(attachments),
            ),
        }
    ]
