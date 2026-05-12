from __future__ import annotations

from typing import Any, Iterable


_CAMEL_CASE_KEYS = {
    "continuation_attempted": "continuationAttempted",
    "continuation_status": "continuationStatus",
    "approval_id": "approvalId",
    "action_id": "actionId",
    "provider_session_kind": "providerSessionKind",
    "provider_call_id": "providerCallId",
    "function_call_name": "functionCallName",
    "provider_tool_type": "providerToolType",
    "retry_without_previous_response_id": "retryWithoutPreviousResponseId",
    "degraded_reason": "degradedReason",
}
_TERMINAL_STATUSES = {
    "completed",
    "degraded",
    "failed",
    "provider_rejected_context",
    "missing_context",
    "missing_runtime",
    "tool_output_shape_error",
}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata(item: Any) -> dict[str, Any]:
    return _dict(getattr(item, "metadata", None))


def _tool_event_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return _dict(item.get("payload"))
    return _dict(getattr(item, "payload", None))


def continuation_from_tool_events(tool_events: Iterable[Any] | None) -> dict[str, Any]:
    for item in list(tool_events or []):
        continuation = _tool_event_payload(item).get("continuation")
        if isinstance(continuation, dict) and continuation:
            return dict(continuation)
    return {}


def continuation_summary(continuation: Any) -> dict[str, Any]:
    payload = _dict(continuation)
    if not payload:
        return {}
    status = str(payload.get("continuation_status") or "").strip()
    summary: dict[str, Any] = {
        "continuation_attempted": bool(payload.get("continuation_attempted")),
        "continuation_status": status,
    }
    for key in (
        "approval_id",
        "action_id",
        "provider_session_kind",
        "provider_call_id",
        "function_call_name",
        "provider_tool_type",
        "degraded_reason",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            summary[key] = value
    if bool(payload.get("retry_without_previous_response_id")):
        summary["retry_without_previous_response_id"] = True
    error = str(payload.get("error") or "").strip()
    if error:
        summary["error"] = error
    return summary


def continuation_status_from_metadata(*, ticket: Any, action_request: Any | None = None) -> dict[str, Any]:
    ticket_metadata = _metadata(ticket)
    action_metadata = _metadata(action_request)
    result = _dict(action_metadata.get("approval_continuation_result")) or _dict(
        ticket_metadata.get("approval_continuation_result")
    )
    pending = _dict(action_metadata.get("pending_tool_continuation")) or _dict(
        ticket_metadata.get("pending_tool_continuation")
    )
    summary = continuation_summary(result)
    if summary:
        status = str(summary.get("continuation_status") or "").strip()
        summary["continuation_stale"] = status not in _TERMINAL_STATUSES
        summary["continuation_source"] = "result"
        return summary
    if pending:
        ticket_status = str(getattr(ticket, "status", "") or "").strip().lower()
        status = "pending" if ticket_status == "pending" else "stale_pending"
        return {
            "continuation_attempted": False,
            "continuation_status": status,
            "approval_id": str(pending.get("approval_id") or getattr(ticket, "approval_id", "") or "").strip(),
            "action_id": str(pending.get("action_id") or getattr(ticket, "action_id", "") or "").strip(),
            "provider_session_kind": str(pending.get("provider_session_kind") or "").strip(),
            "provider_call_id": str(pending.get("provider_call_id") or "").strip(),
            "function_call_name": str(pending.get("function_call_name") or "").strip(),
            "provider_tool_type": str(pending.get("provider_tool_type") or "").strip(),
            "continuation_stale": status == "stale_pending",
            "continuation_source": "pending",
        }
    return {}


def continuation_fields(
    *,
    continuation: Any = None,
    tool_events: Iterable[Any] | None = None,
) -> dict[str, Any]:
    summary = continuation_summary(continuation)
    if not summary:
        summary = continuation_summary(continuation_from_tool_events(tool_events))
    if not summary:
        return {}
    return {
        "continuation": dict(summary),
        "continuation_attempted": bool(summary.get("continuation_attempted")),
        "continuation_status": str(summary.get("continuation_status") or ""),
    }


def camel_case_continuation_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = _dict(fields)
    if not payload:
        return {}
    projected: dict[str, Any] = {}
    continuation = continuation_summary(payload.get("continuation"))
    if continuation:
        projected["continuation"] = {
            _CAMEL_CASE_KEYS.get(key, key): value
            for key, value in continuation.items()
        }
    for snake_key, camel_key in _CAMEL_CASE_KEYS.items():
        if snake_key in payload:
            value = payload[snake_key]
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            projected[camel_key] = value
    return projected
