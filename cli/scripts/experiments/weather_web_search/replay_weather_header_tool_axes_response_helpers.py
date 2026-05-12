from __future__ import annotations

import json
from typing import Any

from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_model_helpers import (
    WEATHER_DETAIL_MARKERS,
)


def _parse_event_stream(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    data_lines: list[str] = []
    event_name = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                data_text = "\n".join(data_lines).strip()
                if data_text and data_text != "[DONE]":
                    try:
                        payload = json.loads(data_text)
                    except json.JSONDecodeError:
                        payload = {"_event": event_name, "_raw": data_text}
                    if isinstance(payload, dict):
                        if event_name and "type" not in payload:
                            payload = {"type": event_name, **payload}
                        events.append(payload)
                data_lines = []
                event_name = ""
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.partition(":")[2].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.partition(":")[2].lstrip())
    if data_lines:
        data_text = "\n".join(data_lines).strip()
        if data_text and data_text != "[DONE]":
            payload = json.loads(data_text)
            if isinstance(payload, dict):
                if event_name and "type" not in payload:
                    payload = {"type": event_name, **payload}
                events.append(payload)
    return events


def _extract_response_items(payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
    response_id = ""
    output_text = ""
    completed_output: list[dict[str, Any]] = []
    streamed_output: list[dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if isinstance(payload.get("id"), str) and not response_id:
            response_id = str(payload.get("id") or "").strip()
        output = payload.get("output")
        if isinstance(output, list):
            completed_output = [item for item in output if isinstance(item, dict)]
            response_id = str(payload.get("id") or response_id or "").strip()
            output_text = str(payload.get("output_text") or output_text or "").strip()
        event_type = str(payload.get("type") or "").strip()
        if event_type == "response.completed":
            response = payload.get("response")
            if isinstance(response, dict):
                response_id = str(response.get("id") or response_id or "").strip()
                output = response.get("output")
                if isinstance(output, list):
                    completed_output = [item for item in output if isinstance(item, dict)]
                output_text = str(response.get("output_text") or output_text or "").strip()
        if event_type in {"response.output_item.done", "response.output_item.added"}:
            item = payload.get("item")
            if isinstance(item, dict):
                streamed_output.append(item)
    items = completed_output or streamed_output
    if not output_text:
        output_text = _extract_message_text(items)
    return items, output_text, response_id


def _extract_message_text(items: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for item in items:
        if str(item.get("type") or "").strip() != "message":
            continue
        for content_item in list(item.get("content") or []):
            if not isinstance(content_item, dict):
                continue
            if str(content_item.get("type") or "").strip() == "output_text":
                text = str(content_item.get("text") or "").strip()
                if text:
                    texts.append(text)
    return texts[-1] if texts else ""


def _classify_result(items: list[dict[str, Any]], output_text: str) -> dict[str, Any]:
    item_types = [str(item.get("type") or "").strip() for item in items if str(item.get("type") or "").strip()]
    web_items = [item for item in items if str(item.get("type") or "").strip() == "web_search_call"]
    queries = [
        str((dict(item.get("action") or {})).get("query") or "").strip()
        for item in web_items
        if str((dict(item.get("action") or {})).get("query") or "").strip()
    ]
    text = str(output_text or "").strip()
    detail_marker_count = sum(1 for marker in WEATHER_DETAIL_MARKERS if marker in text)
    weather_answer_like = len(text) >= 60 and detail_marker_count >= 2
    return {
        "item_types": item_types,
        "web_search_count": len(web_items),
        "web_queries": queries,
        "output_text": text,
        "output_len": len(text),
        "short_no_web": len(web_items) == 0 and len(text) <= 120,
        "weather_answer_like": weather_answer_like,
        "detail_marker_count": detail_marker_count,
    }
