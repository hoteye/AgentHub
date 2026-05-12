from __future__ import annotations

from cli.agent_cli.models import PromptResponse, ResponseInputItem
from cli.agent_cli.ui import transcript_controller_projection_runtime

_TRANSCRIPT_OPERATOR_COMMANDS = frozenset(
    {
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
        "workflows",
        "background_tasks",
        "background_worker_status",
        "background_worker_start",
        "background_worker_stop",
        "background_worker_run_once",
    }
)


def _apply_operator_transcript_projection(controller, response: PromptResponse) -> None:
    command_name = controller._operator_command_name(getattr(response, "user_text", ""))
    if command_name not in _TRANSCRIPT_OPERATOR_COMMANDS:
        return
    raw_assistant_text = str(getattr(response, "assistant_text", "") or "")
    key_values = controller._key_value_lines(getattr(response, "assistant_text", ""))
    projected_text = _operator_transcript_text(
        controller,
        command_name,
        key_values=key_values,
        assistant_text=getattr(response, "assistant_text", ""),
    )
    if not projected_text:
        return
    response._ui_operator_raw_assistant_text = raw_assistant_text
    response.assistant_text = projected_text
    response.response_items = _project_operator_response_items(
        list(getattr(response, "response_items", []) or []),
        projected_text=projected_text,
    )
    response.turn_events = _project_operator_turn_events(
        list(getattr(response, "turn_events", []) or []),
        projected_text=projected_text,
    )


def _project_operator_response_items(
    items: list[ResponseInputItem],
    *,
    projected_text: str,
) -> list[ResponseInputItem]:
    return transcript_controller_projection_runtime.project_operator_response_items(
        items,
        projected_text=projected_text,
    )


def _project_operator_turn_events(
    events: list[dict[str, object]],
    *,
    projected_text: str,
) -> list[dict[str, object]]:
    return transcript_controller_projection_runtime.project_operator_turn_events(
        events,
        projected_text=projected_text,
    )


def _operator_transcript_text(
    controller,
    command_name: str,
    *,
    key_values: dict[str, str],
    assistant_text: str,
) -> str:
    summary = str(
        controller._operator_hint_from_command(
            command_name,
            key_values=key_values,
            assistant_text=assistant_text,
        )
        or ""
    ).strip()
    detail_lines = _operator_transcript_detail_lines(
        controller,
        command_name,
        key_values=key_values,
        assistant_text=assistant_text,
    )
    return transcript_controller_projection_runtime.operator_transcript_text(
        summary=summary,
        detail_lines=detail_lines,
        assistant_text=assistant_text,
    )


def _operator_transcript_detail_lines(
    controller,
    command_name: str,
    *,
    key_values: dict[str, str],
    assistant_text: str,
) -> list[str]:
    return transcript_controller_projection_runtime.operator_transcript_detail_lines(
        command_name,
        key_values=key_values,
        assistant_text=assistant_text,
        workflow_detail_lines_fn=controller._operator_workflow_detail_lines,
        background_task_detail_lines_fn=controller._operator_background_task_detail_lines,
        single_operator_detail_line_fn=controller._single_operator_detail_line,
    )


def _operator_pipe_segments(raw_line: str) -> list[str]:
    return transcript_controller_projection_runtime.operator_pipe_segments(raw_line)


def _operator_segment_map(segments: list[str]) -> tuple[list[str], dict[str, str]]:
    return transcript_controller_projection_runtime.operator_segment_map(segments)


def _operator_workflow_detail_lines(controller, assistant_text: str) -> list[str]:
    return transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)


def _operator_background_task_detail_lines(controller, assistant_text: str) -> list[str]:
    return transcript_controller_projection_runtime.operator_background_task_detail_lines(
        assistant_text
    )


def _single_operator_detail_line(controller, command_name: str, key_values: dict[str, str]) -> str:
    return transcript_controller_projection_runtime.single_operator_detail_line(
        command_name, key_values
    )
