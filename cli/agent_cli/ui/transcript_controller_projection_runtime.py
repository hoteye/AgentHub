from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.ui import transcript_controller_projection_parse_runtime as projection_parse_runtime
from cli.agent_cli.ui import (
    transcript_controller_projection_render_helpers_runtime as projection_render_helpers_runtime,
)


def project_operator_response_items(
    items: list[ResponseInputItem],
    *,
    projected_text: str,
) -> list[ResponseInputItem]:
    projected_items: list[ResponseInputItem] = []
    for item in list(items or []):
        phase = str((getattr(item, "extra", {}) or {}).get("phase") or "").strip().lower()
        is_assistant_message = (
            str(getattr(item, "role", "") or "").strip().lower() == "assistant"
            or str(getattr(item, "item_type", "") or "").strip().lower() == "message"
        )
        if is_assistant_message and phase != "commentary":
            projected_items.append(
                ResponseInputItem(
                    item_type=str(getattr(item, "item_type", "") or "message"),
                    role=str(getattr(item, "role", "") or "assistant"),
                    content=[{"type": "output_text", "text": projected_text}],
                    content_present=True,
                    extra=dict(getattr(item, "extra", {}) or {}),
                )
            )
            continue
        projected_items.append(item)
    return projected_items


def project_operator_turn_events(
    events: list[dict[str, object]],
    *,
    projected_text: str,
) -> list[dict[str, object]]:
    projected_events: list[dict[str, object]] = []
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if (
            isinstance(item, dict)
            and str(item.get("type") or "").strip() == "agent_message"
            and str(item.get("phase") or "").strip().lower() != "commentary"
        ):
            projected_events.append(
                {
                    **dict(event),
                    "item": {
                        **dict(item),
                        "text": projected_text,
                    },
                }
            )
            continue
        projected_events.append(dict(event))
    return projected_events


def operator_transcript_text(
    *,
    summary: str,
    detail_lines: list[str],
    assistant_text: str,
) -> str:
    lines = [line for line in [str(summary or "").strip(), *detail_lines] if str(line or "").strip()]
    if lines:
        return "\n".join(lines)
    return str(assistant_text or "").strip()


def operator_transcript_detail_lines(
    command_name: str,
    *,
    key_values: dict[str, str],
    assistant_text: str,
    workflow_detail_lines_fn: Any,
    background_task_detail_lines_fn: Any,
    single_operator_detail_line_fn: Any,
) -> list[str]:
    if command_name == "workflows":
        return workflow_detail_lines_fn(assistant_text)
    if command_name == "background_tasks":
        return background_task_detail_lines_fn(assistant_text)
    if command_name in {
        "agent_workflow",
        "spawn_agent",
        "wait_agent",
        "send_input",
        "resume_agent",
        "close_agent",
        "background_task_status",
        "background_task_apply",
        "background_task_reject",
        "background_task_cancel",
        "background_task_retry",
    }:
        line = single_operator_detail_line_fn(command_name, key_values)
        return [line] if line else []
    return []


def operator_pipe_segments(raw_line: str) -> list[str]:
    return projection_parse_runtime.operator_pipe_segments(raw_line)


def operator_segment_map(segments: list[str]) -> tuple[list[str], dict[str, str]]:
    return projection_parse_runtime.operator_segment_map(segments)


def _prefixed_token(value: str) -> str:
    return projection_parse_runtime.prefixed_token(value)


def _workflow_detail_identity(keyed: dict[str, str]) -> tuple[str, str, str]:
    return projection_parse_runtime.workflow_detail_identity(keyed)


def _workflow_next_op(
    *,
    workflow_type: str,
    run_id: str,
    card_id: str,
    task_id: str,
    action_name: str,
    workflow_state: str,
    phase: str,
    status: str,
) -> str:
    return projection_render_helpers_runtime.workflow_next_op(
        workflow_type=workflow_type,
        run_id=run_id,
        card_id=card_id,
        task_id=task_id,
        action_name=action_name,
        workflow_state=workflow_state,
        phase=phase,
        status=status,
    )


def _policy_surface(value: Any) -> str:
    return projection_render_helpers_runtime.policy_surface(value)


def _json_compact(value: Any) -> Any:
    return projection_render_helpers_runtime.json_compact(value)


def _mapping_compact(value: Any) -> dict[str, Any]:
    return projection_render_helpers_runtime.mapping_compact(value)


def _workflow_nested_value(keyed: dict[str, str], key: str) -> Any:
    return projection_render_helpers_runtime.workflow_nested_value(keyed, key)


def _count_compact(value: Any) -> int:
    return projection_render_helpers_runtime.count_compact(value)


def _string_items_compact(value: Any) -> list[str]:
    return projection_render_helpers_runtime.string_items_compact(value)


def _card_ids_compact(value: Any) -> list[str]:
    return projection_render_helpers_runtime.card_ids_compact(value)


def _preview_items(items: list[str], *, limit: int = 3) -> str:
    return projection_render_helpers_runtime.preview_items(items, limit=limit)


def _operator_next_command(value: Any) -> str:
    return projection_render_helpers_runtime.operator_next_command(value)


def _followup_summary(value: Any) -> tuple[int, str, str]:
    return projection_render_helpers_runtime.followup_summary(value, preview_items_fn=_preview_items)


def operator_workflow_detail_lines(assistant_text: str) -> list[str]:
    return projection_render_helpers_runtime.operator_workflow_detail_lines(
        assistant_text,
        operator_pipe_segments_fn=operator_pipe_segments,
        operator_segment_map_fn=operator_segment_map,
        workflow_detail_identity_fn=_workflow_detail_identity,
        workflow_next_op_fn=_workflow_next_op,
        workflow_nested_value_fn=_workflow_nested_value,
        count_compact_fn=_count_compact,
        string_items_compact_fn=_string_items_compact,
        card_ids_compact_fn=_card_ids_compact,
        preview_items_fn=_preview_items,
        operator_next_command_fn=_operator_next_command,
        followup_summary_fn=_followup_summary,
        policy_surface_fn=_policy_surface,
    )


def operator_background_task_detail_lines(assistant_text: str) -> list[str]:
    return projection_render_helpers_runtime.operator_background_task_detail_lines(
        assistant_text,
        operator_pipe_segments_fn=operator_pipe_segments,
        operator_segment_map_fn=operator_segment_map,
        policy_surface_fn=_policy_surface,
    )


def single_operator_detail_line(command_name: str, key_values: dict[str, str]) -> str:
    return projection_render_helpers_runtime.single_operator_detail_line(
        command_name,
        key_values,
        policy_surface_fn=_policy_surface,
    )
