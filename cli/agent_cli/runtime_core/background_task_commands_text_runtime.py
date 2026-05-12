from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import (
    background_task_commands_text_runtime_render_helpers as _render_helpers,
    background_task_commands_text_runtime_status_helpers as _status_helpers,
)
from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime import (
    append_bootstrap_lines as _append_bootstrap_lines,
    append_lifecycle_lines as _append_lifecycle_lines,
    append_observability_surface_lines as _append_observability_surface_lines,
    observability_trace_from_route_report as _observability_trace_from_route_report,
)


def _mapping(value: Any) -> dict[str, Any]:
    return _status_helpers._mapping(value)


def _structured_text_value(value: Any) -> str:
    return _status_helpers._structured_text_value(value)


def _structured_state_value(*sources: dict[str, Any], key: str) -> str:
    return _status_helpers._structured_state_value(*sources, key=key)


def _structured_bool_value(*sources: dict[str, Any], key: str) -> bool | None:
    return _status_helpers._structured_bool_value(*sources, key=key)


def _structured_lower_state_value(*sources: dict[str, Any], key: str) -> str:
    return _status_helpers._structured_lower_state_value(*sources, key=key)


def _background_evidence_result_state(
    *,
    payload: dict[str, Any],
    lifecycle: dict[str, Any],
    artifact: dict[str, Any],
    result: dict[str, Any],
    result_artifact: dict[str, Any],
) -> str:
    return _status_helpers._background_evidence_result_state(
        payload=payload,
        lifecycle=lifecycle,
        artifact=artifact,
        result=result,
        result_artifact=result_artifact,
    )


def submitted_task_text(
    *,
    title: str,
    handle: Any,
    detail_pairs: list[tuple[str, Any]],
) -> str:
    return _render_helpers.submitted_task_text(
        title=title,
        handle=handle,
        detail_pairs=detail_pairs,
    )


def background_task_status_text(payload: dict[str, Any], *, task_id: str) -> str:
    return _status_helpers.background_task_status_text(
        payload,
        task_id=task_id,
        mapping_fn=_mapping,
        structured_state_value_fn=_structured_state_value,
        structured_bool_value_fn=_structured_bool_value,
        background_evidence_result_state_fn=_background_evidence_result_state,
        append_lifecycle_lines_fn=_append_lifecycle_lines,
        append_bootstrap_lines_fn=_append_bootstrap_lines,
        append_observability_surface_lines_fn=_append_observability_surface_lines,
        observability_trace_from_route_report_fn=_observability_trace_from_route_report,
    )


def background_task_apply_text(payload: dict[str, Any], *, task_id: str) -> str:
    return _render_helpers.background_task_apply_text(payload, task_id=task_id)


def background_task_reject_text(payload: dict[str, Any], *, task_id: str) -> str:
    return _render_helpers.background_task_reject_text(payload, task_id=task_id)


def background_task_cancel_text(payload: dict[str, Any], *, task_id: str) -> str:
    return _render_helpers.background_task_cancel_text(payload, task_id=task_id)


def background_task_retry_text(payload: dict[str, Any], *, task_id: str) -> str:
    return _render_helpers.background_task_retry_text(payload, task_id=task_id)


def background_teammate_submission_text(
    *,
    handle: Any,
    provider: str,
    model: str,
    reasoning_effort: str,
    allowed_paths: list[str],
    blocked_paths: list[str],
    timeout_seconds: float | None,
    task_text: str,
    preview_text_fn: Callable[..., str],
) -> str:
    return _render_helpers.background_teammate_submission_text(
        handle=handle,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        timeout_seconds=timeout_seconds,
        task_text=task_text,
        preview_text_fn=preview_text_fn,
    )
