from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_live_harness_model_helpers import LiveCase
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from approval_continuation_live_harness_model_helpers import LiveCase  # type: ignore[no-redef]


def _response_payload(line: dict[str, Any]) -> dict[str, Any]:
    return dict(line.get("response") or {})


def _tool_events(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(response.get("tool_events") or []) if isinstance(item, dict)]


def _extract_approval_id(response: dict[str, Any]) -> str:
    for event in _tool_events(response):
        name = str(event.get("name") or "").strip()
        payload = dict(event.get("payload") or {})
        if name.endswith("_approval_requested"):
            approval_id = str(payload.get("approval_id") or "").strip()
            if approval_id:
                return approval_id
    return ""


def _extract_continuation(response: dict[str, Any]) -> dict[str, Any]:
    for event in _tool_events(response):
        payload = dict(event.get("payload") or {})
        continuation = payload.get("continuation")
        if isinstance(continuation, dict):
            return dict(continuation)
    return {}


def _text_preview(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "..."


def _summarize_tool_output_items(items: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        output = item.get("output")
        summaries.append(
            {
                "type": str(item.get("type") or "").strip(),
                "call_id": str(item.get("call_id") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "success": item.get("success") if isinstance(item.get("success"), bool) else None,
                "output_preview": _text_preview(output),
            }
        )
    return summaries


def _summarize_continuation(continuation: dict[str, Any]) -> dict[str, Any]:
    if not continuation:
        return {}
    tool_output_items = _summarize_tool_output_items(continuation.get("tool_output_items"))
    provider_call_id = str(continuation.get("provider_call_id") or "").strip()
    if not provider_call_id and tool_output_items:
        provider_call_id = str(tool_output_items[0].get("call_id") or "").strip()
    return {
        "continuation_attempted": bool(continuation.get("continuation_attempted")),
        "continuation_status": str(continuation.get("continuation_status") or "").strip(),
        "previous_response_id_present": bool(str(continuation.get("previous_response_id") or "").strip()),
        "provider_call_id": provider_call_id,
        "function_call_name": str(continuation.get("function_call_name") or "").strip(),
        "provider_tool_type": str(continuation.get("provider_tool_type") or "").strip(),
        "tool_output_items": tool_output_items,
        "retry_without_previous_response_id": bool(continuation.get("retry_without_previous_response_id")),
        "assistant_text": str(continuation.get("assistant_text") or "").strip(),
        "error": _text_preview(continuation.get("error")),
    }


def _input_item_type(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    item_type = str(item.get("type") or "").strip()
    if item_type:
        return item_type
    role = str(item.get("role") or "").strip()
    return f"message:{role}" if role else ""


def _request_log_summary(log_dir: Path) -> dict[str, Any]:
    path = log_dir / "llm_io.jsonl"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return {
            "path": str(path),
            "request_count": 0,
            "requests": [],
        }
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("stage") or "") != "responses.send.request_raw":
            continue
        request = dict(dict(row.get("payload") or {}).get("request") or {})
        input_items = [dict(item) for item in list(request.get("input") or []) if isinstance(item, dict)]
        rows.append(
            {
                "previous_response_id": str(request.get("previous_response_id") or ""),
                "input_types": [item_type for item_type in (_input_item_type(item) for item in input_items) if item_type],
                "tool_names": [
                    str(tool.get("name") or "").strip()
                    for tool in list(request.get("tools") or [])
                    if isinstance(tool, dict) and str(tool.get("name") or "").strip()
                ],
                "function_call_output_call_ids": [
                    str(item.get("call_id") or "").strip()
                    for item in input_items
                    if str(item.get("type") or "").strip()
                    in {"function_call_output", "custom_tool_call_output", "shell_call_output", "local_shell_call_output"}
                ],
            }
        )
    return {
        "path": str(path),
        "request_count": len(rows),
        "requests": rows,
    }


def _case_verdict(
    *,
    case: LiveCase,
    first_response: dict[str, Any],
    decision_response: dict[str, Any],
    continuation: dict[str, Any],
    workspace: Path,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    approval_id = _extract_approval_id(first_response)
    if not approval_id:
        reasons.append("missing_approval_id")
    first_event_names = {str(event.get("name") or "").strip() for event in _tool_events(first_response)}
    expected_approval_event = (
        "patch_approval_requested" if case.tool_name == "apply_patch" else "shell_approval_requested"
    )
    if expected_approval_event not in first_event_names:
        reasons.append(f"missing_{expected_approval_event}")
    if str(continuation.get("continuation_status") or "") != "completed":
        reasons.append("continuation_not_completed")
    if not bool(continuation.get("continuation_attempted")):
        reasons.append("continuation_not_attempted")
    if not str(continuation.get("assistant_text") or decision_response.get("assistant_text") or "").strip():
        reasons.append("missing_resumed_assistant_text")
    target = workspace / case.target_file
    if case.decision == "approve":
        if not target.exists():
            reasons.append("approved_file_missing")
        else:
            actual = target.read_text(encoding="utf-8").strip()
            if actual != case.expected_content:
                reasons.append("approved_file_content_mismatch")
    else:
        if target.exists():
            reasons.append("rejected_file_should_not_exist")
    return ("pass" if not reasons else "fail", reasons)
