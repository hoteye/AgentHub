from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.models import response_items_phase_text, response_items_to_text
from cli.agent_cli.runtime_services.expert_review_packet_projection_normalization_helpers_runtime import (
    _extract_paths,
    _normalize_tool_output,
    _response_items_from_turn,
)
from cli.agent_cli.runtime_services.expert_review_packet_projection_pure_helpers_runtime import (
    MAX_ARGUMENT_CHARS,
    MAX_ARTIFACT_PATHS,
    MAX_EVIDENCE_TEXT_CHARS,
    MAX_TEST_EVIDENCE,
    MAX_TOOL_RESULT_CHARS,
    clip_text,
    _content_text,
    _dedupe_strings,
    _json_preview,
    _mapping_text,
)


_TOOL_TURN_ITEM_TYPES = {
    "mcp_tool_call",
    "command_execution",
    "web_search_call",
    "function_call",
    "custom_tool_call",
}


def _assistant_text_from_turn(turn: dict[str, Any]) -> str:
    assistant_history_text = str(turn.get("assistant_history_text") or "").strip()
    if assistant_history_text:
        return assistant_history_text
    assistant_text = str(turn.get("assistant_text") or "").strip()
    if assistant_text:
        return assistant_text
    response_items = _response_items_from_turn(turn)
    final_phase_text = response_items_phase_text(response_items, phase="final_answer")
    if final_phase_text:
        return final_phase_text.strip()
    visible_items = []
    for item in response_items:
        phase = str((item.extra or {}).get("phase") or "").strip().lower()
        item_type = str(getattr(item, "item_type", "") or "").strip().lower()
        if phase == "commentary" or item_type == "reasoning":
            continue
        role = str(getattr(item, "role", "") or "").strip().lower()
        if role and role != "assistant":
            continue
        visible_items.append(item)
    return response_items_to_text(visible_items).strip()


def _tool_activity_from_turn(
    turn: dict[str, Any],
    *,
    turn_id: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    turn_events = [dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, Mapping)]
    for event in turn_events:
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, Mapping):
            continue
        projected = _tool_activity_from_turn_item(dict(item), turn_id=turn_id)
        if projected is not None:
            entries.append(projected)
    if entries:
        return entries
    for raw_tool_event in list(turn.get("tool_events") or []):
        projected = _tool_activity_from_tool_output(raw_tool_event, turn_id=turn_id)
        if projected is not None:
            entries.append(projected)
    return entries


def _tool_activity_from_turn_item(
    item: dict[str, Any],
    *,
    turn_id: str,
) -> dict[str, Any] | None:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type not in _TOOL_TURN_ITEM_TYPES:
        return None
    if item_type == "command_execution":
        arguments_preview, arguments_truncated = clip_text(
            item.get("command"),
            max_chars=MAX_ARGUMENT_CHARS,
        )
        result_preview, result_truncated = clip_text(
            item.get("aggregated_output"),
            max_chars=MAX_TOOL_RESULT_CHARS,
        )
        return {
            "source": "turn",
            "turn_id": turn_id,
            "kind": item_type,
            "name": "shell",
            "status": str(item.get("status") or "").strip() or "completed",
            "call_id": str(item.get("call_id") or item.get("id") or "").strip(),
            "arguments_preview": arguments_preview,
            "arguments_truncated": arguments_truncated,
            "result_preview": result_preview,
            "result_truncated": result_truncated,
            "artifact_paths": _dedupe_strings(_extract_paths(item), limit=MAX_ARTIFACT_PATHS),
            "exit_code": item.get("exit_code"),
        }
    if item_type == "web_search_call":
        arguments_preview, arguments_truncated = clip_text(
            item.get("query"),
            max_chars=MAX_ARGUMENT_CHARS,
        )
        result_preview, result_truncated = clip_text(
            item.get("search_phase"),
            max_chars=MAX_TOOL_RESULT_CHARS,
        )
        return {
            "source": "turn",
            "turn_id": turn_id,
            "kind": item_type,
            "name": "web_search",
            "status": str(item.get("status") or "").strip() or "completed",
            "call_id": str(item.get("call_id") or item.get("id") or "").strip(),
            "arguments_preview": arguments_preview,
            "arguments_truncated": arguments_truncated,
            "result_preview": result_preview,
            "result_truncated": result_truncated,
            "artifact_paths": _dedupe_strings(_extract_paths(item), limit=MAX_ARTIFACT_PATHS),
        }
    arguments_preview, arguments_truncated = clip_text(
        _json_preview(item.get("arguments")),
        max_chars=MAX_ARGUMENT_CHARS,
    )
    result_preview, result_truncated = clip_text(
        _tool_result_preview_from_turn_item(item),
        max_chars=MAX_TOOL_RESULT_CHARS,
    )
    return {
        "source": "turn",
        "turn_id": turn_id,
        "kind": item_type,
        "name": str(item.get("tool") or item.get("name") or "").strip(),
        "status": str(item.get("status") or "").strip() or "completed",
        "call_id": str(item.get("call_id") or item.get("id") or "").strip(),
        "arguments_preview": arguments_preview,
        "arguments_truncated": arguments_truncated,
        "result_preview": result_preview,
        "result_truncated": result_truncated,
        "artifact_paths": _dedupe_strings(_extract_paths(item), limit=MAX_ARTIFACT_PATHS),
    }


def _tool_result_preview_from_turn_item(item: dict[str, Any]) -> str:
    error = item.get("error")
    if isinstance(error, Mapping):
        message = str(error.get("message") or error.get("error") or "").strip()
        if message:
            return message
    result = item.get("result")
    if not isinstance(result, Mapping):
        return ""
    content = result.get("content")
    content_text = _content_text(content)
    if content_text:
        return content_text
    structured = result.get("structured_content")
    if isinstance(structured, Mapping):
        for key in ("text", "output_text", "stdout", "summary_text", "summary", "detail"):
            text = _mapping_text(structured.get(key))
            if text:
                return text
        return _json_preview(structured)
    return ""


def _tool_activity_from_tool_output(
    raw_tool_event: Any,
    *,
    turn_id: str = "",
) -> dict[str, Any] | None:
    tool_event = _normalize_tool_output(raw_tool_event)
    if not tool_event:
        return None
    payload = tool_event.get("payload")
    payload_map = dict(payload) if isinstance(payload, Mapping) else {}
    arguments_preview, arguments_truncated = clip_text(
        _json_preview(payload_map.get("arguments") or payload_map.get("input") or payload_map.get("command")),
        max_chars=MAX_ARGUMENT_CHARS,
    )
    summary_preview, summary_truncated = clip_text(
        tool_event.get("summary"),
        max_chars=MAX_TOOL_RESULT_CHARS,
    )
    result_preview, result_truncated = clip_text(
        _tool_result_preview_from_payload(payload_map) or tool_event.get("summary"),
        max_chars=MAX_TOOL_RESULT_CHARS,
    )
    return {
        "source": "tool_output",
        "turn_id": turn_id,
        "kind": "tool_event",
        "name": str(tool_event.get("name") or "").strip(),
        "status": "completed" if bool(tool_event.get("ok")) else "failed",
        "call_id": str(payload_map.get("provider_call_id") or payload_map.get("call_id") or "").strip(),
        "summary": summary_preview,
        "summary_truncated": summary_truncated,
        "arguments_preview": arguments_preview,
        "arguments_truncated": arguments_truncated,
        "result_preview": result_preview,
        "result_truncated": result_truncated,
        "artifact_paths": _dedupe_strings(_extract_paths(payload_map), limit=MAX_ARTIFACT_PATHS),
    }


def _tool_result_preview_from_payload(payload: dict[str, Any]) -> str:
    for key in ("text", "output_text", "stdout", "summary_text", "error", "message"):
        text = _mapping_text(payload.get(key))
        if text:
            return text
    return ""


def _dedupe_tool_activity(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for entry in entries:
        key = (
            str(entry.get("turn_id") or ""),
            str(entry.get("call_id") or ""),
            str(entry.get("kind") or ""),
            str(entry.get("name") or ""),
            str(entry.get("result_preview") or entry.get("summary") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _test_evidence_projection(runtime_state: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    raw_entries = []
    for key in ("test_evidence", "command_evidence"):
        value = runtime_state.get(key)
        if isinstance(value, list):
            raw_entries.extend(value)
    projected: list[dict[str, Any]] = []
    for entry in raw_entries:
        if isinstance(entry, Mapping):
            label = str(
                entry.get("label")
                or entry.get("command")
                or entry.get("name")
                or entry.get("summary")
                or ""
            ).strip()
            status = str(entry.get("status") or entry.get("result") or "").strip()
            text_source = (
                entry.get("text")
                or entry.get("output")
                or entry.get("stdout")
                or entry.get("stderr")
                or entry.get("summary")
                or ""
            )
        else:
            label = ""
            status = ""
            text_source = entry
        text, truncated = clip_text(text_source, max_chars=MAX_EVIDENCE_TEXT_CHARS)
        payload: dict[str, Any] = {
            "text": text,
            "truncated": truncated,
        }
        if label:
            payload["label"] = label
        if status:
            payload["status"] = status
        projected.append(payload)
    return projected[:MAX_TEST_EVIDENCE], len(projected) > MAX_TEST_EVIDENCE


__all__ = [
    "_TOOL_TURN_ITEM_TYPES",
    "_assistant_text_from_turn",
    "_dedupe_tool_activity",
    "_test_evidence_projection",
    "_tool_activity_from_tool_output",
    "_tool_activity_from_turn",
    "_tool_activity_from_turn_item",
    "_tool_result_preview_from_payload",
    "_tool_result_preview_from_turn_item",
]
