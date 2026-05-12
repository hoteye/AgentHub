from __future__ import annotations

from typing import Any, Callable, Dict


def log_responses_request(
    stage: str,
    kwargs: Dict[str, Any],
    *,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    if not timeline_debug_enabled_fn():
        return
    payload = dict(kwargs or {})
    input_items = payload.get("input")
    log_timeline_fn(
        f"{stage}.request_raw",
        request=json_ready_fn(payload),
        input_count=len(list(input_items or [])) if isinstance(input_items, list) else None,
        tool_count=len(list(payload.get("tools") or [])) if isinstance(payload.get("tools"), list) else 0,
        stream=bool(payload.get("stream")),
        previous_response_id=payload.get("previous_response_id"),
    )


def log_responses_response(
    stage: str,
    response: Any,
    *,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    if not timeline_debug_enabled_fn():
        return
    log_timeline_fn(
        f"{stage}.response_raw",
        response=json_ready_fn(response),
        response_id=str(getattr(response, "id", "") or "").strip() or None,
    )
