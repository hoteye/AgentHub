from __future__ import annotations

from typing import Any, Callable


def log_responses_request(
    stage: str,
    kwargs: dict[str, Any],
    *,
    support_runtime: Any,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[[str, Any], None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    support_runtime.log_responses_request(
        stage,
        kwargs,
        timeline_debug_enabled_fn=timeline_debug_enabled_fn,
        log_timeline_fn=log_timeline_fn,
        json_ready_fn=json_ready_fn,
    )


def log_responses_response(
    stage: str,
    response: Any,
    *,
    support_runtime: Any,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[[str, Any], None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    support_runtime.log_responses_response(
        stage,
        response,
        timeline_debug_enabled_fn=timeline_debug_enabled_fn,
        log_timeline_fn=log_timeline_fn,
        json_ready_fn=json_ready_fn,
    )
