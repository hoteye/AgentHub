from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Dict, List

from cli.agent_cli.models import AgentIntent, ToolEvent, default_response_items


_TOOL_DEMO_QUERY_MARKERS = (
    "怎么用",
    "如何用",
    "如何使用",
    "用法",
    "示范",
    "演示",
    "example",
    "demo",
    "how to use",
)


def tool_demo_requested(user_text: str) -> bool:
    text = str(user_text or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _TOOL_DEMO_QUERY_MARKERS)


def _render_tool_usage_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def tool_usage_examples(events: List[ToolEvent]) -> List[str]:
    examples: List[str] = []
    seen: set[tuple[str, str]] = set()
    for event in list(events or []):
        payload = dict(getattr(event, "payload", {}) or {})
        tool_name = str(payload.get("function_call_name") or event.name or "").strip()
        arguments = payload.get("function_call_arguments")
        if not tool_name or not isinstance(arguments, dict) or not arguments:
            continue
        rendered_args = ", ".join(
            f"{key}={_render_tool_usage_value(value)}"
            for key, value in arguments.items()
            if str(key or "").strip()
        )
        if not rendered_args:
            continue
        key = (tool_name, rendered_args)
        if key in seen:
            continue
        seen.add(key)
        examples.append(f"- {tool_name}({rendered_args})")
    return examples


def update_final_response_items(intent: AgentIntent, assistant_text: str) -> List[Any]:
    items = list(intent.response_items or [])
    for item in items:
        if str(getattr(item, "item_type", "") or "").strip() != "message":
            continue
        extra = dict(getattr(item, "extra", {}) or {})
        if str(extra.get("phase") or "").strip() != "final_answer":
            continue
        item.content = [{"type": "output_text", "text": assistant_text}]
        item.content_present = True
        return items
    return [*items, *default_response_items(assistant_text=assistant_text)]


def update_final_turn_events(intent: AgentIntent, assistant_text: str) -> List[Dict[str, Any]]:
    events = [dict(item) for item in list(intent.turn_events or []) if isinstance(item, dict)]
    for event in reversed(events):
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        item["text"] = assistant_text
        return events
    return events


def with_tool_demo_examples(intent: AgentIntent, *, user_text: str) -> AgentIntent:
    if not tool_demo_requested(user_text):
        return intent
    examples = tool_usage_examples(list(intent.tool_events or []))
    if not examples:
        return intent
    appendix = "本次实际示例：\n" + "\n".join(examples)
    assistant_text = str(intent.assistant_text or "").strip()
    if appendix in assistant_text:
        return intent
    updated_text = f"{assistant_text}\n\n{appendix}".strip() if assistant_text else appendix
    return replace(
        intent,
        assistant_text=updated_text,
        response_items=update_final_response_items(intent, updated_text),
        turn_events=update_final_turn_events(intent, updated_text),
    )
