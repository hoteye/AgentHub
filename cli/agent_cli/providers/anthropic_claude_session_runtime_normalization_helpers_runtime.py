from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ResponseInputItem

_TOOL_RESULT_MISSING_PLACEHOLDER = "[Tool result missing due to internal error]"


def normalize_messages(
    input_items: list[dict[str, Any]],
    *,
    tool_result_block_fn: Callable[..., dict[str, Any]],
    message_text_fn: Callable[[Any], str],
    workspace_reference_message_fn: Callable[[dict[str, Any]], str],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
    known_tool_use_ids: set[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []
    pending_tool_uses: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []
    known_tool_ids = {
        str(item or "").strip() for item in (known_tool_use_ids or set()) if str(item or "").strip()
    }

    def tool_use_id(block: dict[str, Any]) -> str:
        return str(block.get("id") or "").strip()

    def tool_result_id(block: dict[str, Any]) -> str:
        return str(block.get("tool_use_id") or block.get("call_id") or "").strip()

    def tool_result_text(block: dict[str, Any]) -> str:
        content = block.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
                elif item is not None:
                    parts.append(str(item).strip())
            if parts:
                return "\n".join(parts).strip()
        elif content is not None:
            if isinstance(content, dict | list):
                return json.dumps(content, ensure_ascii=False)
            return str(content).strip()

        output = block.get("output")
        if isinstance(output, dict | list):
            return json.dumps(output, ensure_ascii=False)
        if output is not None:
            return str(output).strip()
        return ""

    def orphan_tool_result_text(block: dict[str, Any]) -> str:
        call_id = tool_result_id(block) or "unknown"
        output = tool_result_text(block)
        prefix = (
            "[Tool result replayed as plain text because the matching "
            f"tool_use is unavailable: {call_id}]"
        )
        return f"{prefix}\n{output}".strip()

    def append_orphan_tool_results(results: list[dict[str, Any]]) -> None:
        if not results:
            return
        text = "\n\n".join(orphan_tool_result_text(block) for block in results).strip()
        if not text:
            return
        messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
        if timeline_debug_enabled_fn():
            log_timeline_fn(
                "anthropic.replay.tool_result.orphan_converted",
                **json_ready_fn(
                    {
                        "count": len(results),
                        "call_ids": [tool_result_id(block) for block in results],
                    }
                ),
            )

    def ensure_tool_result_pairing() -> list[dict[str, Any]]:
        if not pending_tool_uses:
            known_results: list[dict[str, Any]] = []
            orphan_results: list[dict[str, Any]] = []
            for raw_block in list(pending_tool_results):
                block = dict(raw_block)
                call_id = tool_result_id(block)
                if call_id and call_id in known_tool_ids:
                    known_results.append(block)
                else:
                    orphan_results.append(block)
            pending_tool_results.clear()
            if known_results:
                pending_tool_results.extend(known_results)
            return orphan_results
        ordered_results: list[dict[str, Any]] = []
        unmatched_results: list[dict[str, Any]] = []
        existing_results: dict[str, dict[str, Any]] = {}
        for raw_block in list(pending_tool_results):
            block = dict(raw_block)
            call_id = tool_result_id(block)
            if call_id and call_id not in existing_results:
                existing_results[call_id] = block
            else:
                unmatched_results.append(block)

        missing_call_ids: list[str] = []
        for tool_use in list(pending_tool_uses):
            call_id = tool_use_id(tool_use)
            if not call_id:
                continue
            matched = existing_results.pop(call_id, None)
            if matched is not None:
                ordered_results.append(matched)
                continue
            missing_call_ids.append(call_id)
            ordered_results.append(
                tool_result_block_fn(
                    call_id=call_id,
                    output=_TOOL_RESULT_MISSING_PLACEHOLDER,
                    success=False,
                )
            )

        pending_tool_results.clear()
        if ordered_results:
            pending_tool_results.extend(ordered_results)
        orphan_results = [*existing_results.values(), *unmatched_results]

        if missing_call_ids and timeline_debug_enabled_fn():
            log_timeline_fn(
                "anthropic.replay.tool_result.placeholder_inserted",
                **json_ready_fn(
                    {
                        "count": len(missing_call_ids),
                        "missing_call_ids": missing_call_ids,
                    }
                ),
            )
        return orphan_results

    def flush_tool_uses() -> None:
        if not pending_tool_uses:
            return
        messages.append({"role": "assistant", "content": list(pending_tool_uses)})
        pending_tool_uses.clear()

    def flush_tool_results() -> None:
        orphan_results = ensure_tool_result_pairing()
        if pending_tool_results:
            flush_tool_uses()
            messages.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()
        append_orphan_tool_results(orphan_results)

    def flush_pending_tool_exchange() -> None:
        flush_tool_results()
        flush_tool_uses()

    def append_text_message(role: str, text: str) -> None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        normalized_role = str(role or "").strip().lower()
        if normalized_role in {"system", "developer"}:
            system_parts.append(normalized_text)
            return
        flush_pending_tool_exchange()
        messages.append(
            {
                "role": normalized_role or "user",
                "content": [{"type": "text", "text": normalized_text}],
            }
        )

    def append_tool_use_message(item: dict[str, Any]) -> bool:
        normalized = ResponseInputItem.from_dict(item).to_dict()
        item_type = str(normalized.get("type") or "").strip()
        if item_type not in {"function_call", "custom_tool_call"}:
            return False
        call_id = str(normalized.get("call_id") or normalized.get("id") or "").strip()
        name = str(normalized.get("name") or "").strip()
        if not call_id or not name:
            if timeline_debug_enabled_fn():
                log_timeline_fn(
                    "anthropic.replay.tool_use.skipped",
                    **json_ready_fn(
                        {
                            "reason": "missing_call_id_or_name",
                            "item_type": item_type,
                            "call_id": call_id,
                            "name": name,
                            "item": normalized,
                        }
                    ),
                )
            return False
        tool_input: dict[str, Any] = {}
        if item_type == "function_call":
            arguments = normalized.get("arguments")
            if isinstance(arguments, dict):
                tool_input = dict(arguments)
            elif isinstance(arguments, str) and arguments.strip():
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    if timeline_debug_enabled_fn():
                        log_timeline_fn(
                            "anthropic.replay.tool_use.arguments_decode_failed",
                            **json_ready_fn(
                                {
                                    "call_id": call_id,
                                    "name": name,
                                    "item_type": item_type,
                                    "error": str(exc),
                                    "arguments": arguments,
                                }
                            ),
                        )
                    parsed = {}
                if isinstance(parsed, dict):
                    tool_input = dict(parsed)
        else:
            custom_input = str(normalized.get("input") or "").strip()
            if custom_input:
                tool_input = (
                    {"patch": custom_input} if name == "apply_patch" else {"input": custom_input}
                )
        # Multi-turn replay may rehydrate tool calls as top-level response
        # items. Anthropic requires tool_use blocks from the same assistant turn
        # to remain grouped before the user tool_result message on follow-up turns.
        if pending_tool_results:
            flush_tool_results()
        pending_tool_uses.append(
            {
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": tool_input,
            }
        )
        return True

    for raw in list(input_items or []):
        if not isinstance(raw, dict):
            continue
        item_type = str(raw.get("type") or "").strip()
        if item_type == "reference_context_item":
            payload = raw.get("item")
            if isinstance(payload, dict):
                append_text_message("user", workspace_reference_message_fn(payload))
            continue
        if item_type == "response_item":
            nested = raw.get("item")
            if not isinstance(nested, dict):
                continue
            normalized = ResponseInputItem.from_dict(nested).to_dict()
            nested_type = str(normalized.get("type") or "").strip()
            if append_tool_use_message(normalized):
                continue
            if nested_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(
                    normalized.get("call_id") or normalized.get("tool_call_id") or ""
                ).strip()
                if call_id:
                    pending_tool_results.append(
                        tool_result_block_fn(
                            call_id=call_id,
                            output=normalized.get("output"),
                            success=normalized.get("success"),
                        )
                    )
                continue
            role = str(normalized.get("role") or "assistant").strip() or "assistant"
            append_text_message(role, message_text_fn(normalized.get("content")))
            continue
        if append_tool_use_message(raw):
            continue
        if item_type in {"function_call_output", "custom_tool_call_output"}:
            call_id = str(raw.get("call_id") or raw.get("tool_call_id") or "").strip()
            if call_id:
                pending_tool_results.append(
                    tool_result_block_fn(
                        call_id=call_id,
                        output=raw.get("output"),
                        success=raw.get("success"),
                    )
                )
            continue
        if item_type == "message":
            append_text_message(
                str(raw.get("role") or "user").strip() or "user",
                message_text_fn(raw.get("content")),
            )
            continue
        role = str(raw.get("role") or "").strip()
        if not role:
            continue
        if role == "tool":
            call_id = str(raw.get("tool_call_id") or raw.get("call_id") or "").strip()
            if call_id:
                pending_tool_results.append(
                    tool_result_block_fn(
                        call_id=call_id,
                        output=raw.get("output", raw.get("content")),
                        success=raw.get("success"),
                    )
                )
            continue
        append_text_message(role, message_text_fn(raw.get("content")))

    flush_pending_tool_exchange()
    return system_parts, messages


__all__ = ["normalize_messages"]
