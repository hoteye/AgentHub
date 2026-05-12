from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ResponseInputItem


def assistant_text_from_turn_events(turn_events: Any) -> str:
    events = [dict(item) for item in list(turn_events or []) if isinstance(item, dict)]
    for event in reversed(events):
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            return text
    return ""


def turn_events_have_structured_tool_items(turn_events: Any) -> bool:
    tool_item_types = {
        "command_execution",
        "mcp_tool_call",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
    }
    for event in list(turn_events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() in tool_item_types:
            return True
    return False


def turn_replay_requires_structured_tool_output(tool_events: Any) -> bool:
    for event in list(tool_events or []):
        if isinstance(event, dict):
            event_name = str(event.get("name") or "").strip()
            event_ok = event.get("ok")
        else:
            event_name = str(getattr(event, "name", "") or "").strip()
            event_ok = getattr(event, "ok", None)
        if event_name == "request_user_input":
            return True
        if event_ok is False:
            return True
    return False


def response_items_with_canonical_final_message(
    response_items: list[dict[str, Any]],
    turn_events: Any,
    *,
    assistant_text_from_turn_events_fn: Any,
) -> list[dict[str, Any]]:
    canonical_text = assistant_text_from_turn_events_fn(turn_events)
    updated = [dict(item) for item in list(response_items or []) if isinstance(item, dict)]
    if not canonical_text:
        return updated
    for idx in range(len(updated) - 1, -1, -1):
        raw_item = ResponseInputItem.from_dict(updated[idx]).to_dict()
        if str(raw_item.get("type") or "").strip() != "message":
            continue
        if str(raw_item.get("role") or "").strip() != "assistant":
            continue
        content = [dict(block) for block in list(raw_item.get("content") or []) if isinstance(block, dict)]
        replaced = False
        for block_idx in range(len(content) - 1, -1, -1):
            block = dict(content[block_idx])
            block_type = str(block.get("type") or "").strip()
            if block_type in {"output_text", "input_text", "text"}:
                block["text"] = canonical_text
                content[block_idx] = block
                replaced = True
                break
        if not replaced:
            content.append({"type": "output_text", "text": canonical_text})
        raw_item["content"] = content
        updated[idx] = raw_item
        return updated
    updated.append(
        ResponseInputItem(
            item_type="message",
            role="assistant",
            content=[{"type": "output_text", "text": canonical_text}],
            extra={"phase": "final_answer"},
        ).to_dict()
    )
    return updated


def preferred_assistant_turn_text(
    *,
    turn_events: Any,
    assistant_history_text: str,
    response_item_text: str,
    assistant_fallback_text: str,
    assistant_text_from_turn_events_fn: Any,
    turn_events_have_structured_tool_items_fn: Any,
) -> str:
    canonical_turn_text = assistant_text_from_turn_events_fn(turn_events)
    has_structured_tool_items = turn_events_have_structured_tool_items_fn(turn_events)
    assistant_history_text = str(assistant_history_text or "").strip()
    response_item_text = str(response_item_text or "").strip()
    assistant_fallback_text = str(assistant_fallback_text or "").strip()
    if has_structured_tool_items and canonical_turn_text:
        if assistant_history_text and canonical_turn_text in assistant_history_text:
            if assistant_history_text.startswith(canonical_turn_text):
                return canonical_turn_text
            return assistant_history_text
        if response_item_text and "\n\n" in response_item_text:
            return assistant_history_text or response_item_text
        return canonical_turn_text
    return assistant_history_text or response_item_text or assistant_fallback_text


def turn_used_provider(turn: dict[str, Any], *, turn_events_have_structured_tool_items_fn: Any) -> bool:
    protocol_diagnostics = dict(turn.get("protocol_diagnostics") or {})
    protocol_path = dict(protocol_diagnostics.get("protocol_path") or {})
    if bool(protocol_path.get("provider_used", True)):
        return True
    turn_events = [dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, dict)]
    tool_events = [dict(item) for item in list(turn.get("tool_events") or []) if isinstance(item, dict)]
    return bool(tool_events) or turn_events_have_structured_tool_items_fn(turn_events)
