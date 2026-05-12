from __future__ import annotations

"""Shell protocol normalization for app-server command responses and activity events."""

from functools import partial
from typing import Any

from cli.agent_cli import app_server_shell_protocol_helpers
from cli.agent_cli import app_server_shell_protocol_runtime as app_server_shell_protocol_runtime_service
from cli.agent_cli import headless_runtime as headless_runtime_service
from cli.agent_cli import headless_wiring_runtime as headless_wiring_runtime_service
from cli.agent_cli.models import (
    ActivityEvent,
    PromptResponse,
    prompt_response_turn_events,
    tool_event_is_soft_failure,
    tool_events_to_turn_events,
)

_LIFECYCLE_KIND_BY_PHASE: dict[str, str] = {
    "started": "begin",
    "input": "input",
    "output": "output",
    "completed": "end",
    "spawn_failed": "end",
}


def _shell_event_kind(payload: dict[str, Any] | None) -> str | None:
    lifecycle = _shell_lifecycle_dict(payload)
    kind = str(lifecycle.get("kind") or _LIFECYCLE_KIND_BY_PHASE.get(_shell_phase(payload)) or "").strip()
    return kind or None


def _shell_lifecycle_dict(payload: dict[str, Any] | None) -> dict[str, Any]:
    return app_server_shell_protocol_runtime_service.shell_lifecycle_dict(
        payload,
        infer_shell_phase_fn=_infer_shell_phase,
        lifecycle_kind_by_phase=_LIFECYCLE_KIND_BY_PHASE,
    )


def _shell_phase(payload: dict[str, Any] | None) -> str:
    return str((payload or {}).get("phase") or _shell_lifecycle_dict(payload).get("phase") or "").strip().lower()


def _infer_shell_phase(payload: dict[str, Any] | None, *, lifecycle: dict[str, Any] | None = None) -> str:
    raw = dict(payload or {})
    lifecycle = dict(lifecycle or {})
    explicit = str(raw.get("phase") or lifecycle.get("phase") or "").strip().lower()
    if explicit:
        return explicit
    status = str(raw.get("status") or lifecycle.get("status") or "").strip().lower()
    if raw.get("stdin") is not None or raw.get("chars") is not None or raw.get("interaction_input") is not None:
        return "input"
    if (
        raw.get("text") is not None
        or raw.get("chunk") is not None
        or raw.get("output_chunk") is not None
        or raw.get("output_text") is not None
        or raw.get("stream") is not None
    ):
        return "output"
    if (
        raw.get("returncode") is not None
        or raw.get("exit_code") is not None
        or raw.get("stdout") is not None
        or raw.get("stderr") is not None
        or raw.get("interrupted") is not None
        or raw.get("timed_out") is not None
        or status in {"ok", "error", "timeout", "interrupted", "spawn_failed", "completed"}
    ):
        return "completed"
    if raw.get("session_id") is not None or raw.get("process_id") is not None or raw.get("command") is not None:
        return "started"
    return ""


def _shell_call_id(payload: dict[str, Any] | None) -> str:
    return str(_shell_lifecycle_dict(payload).get("call_id") or (payload or {}).get("call_id") or "").strip()


def _shell_process_id(payload: dict[str, Any] | None, *, session_id: str | None = None) -> str | None:
    return app_server_shell_protocol_helpers.shell_process_id(payload, session_id=session_id)


def _shell_command_text(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_command_text(payload)


def _shell_cwd(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_cwd(payload)


def _shell_status(payload: dict[str, Any] | None) -> str | None:
    phase = _shell_phase(payload)
    lifecycle = _shell_lifecycle_dict(payload)
    explicit = str((payload or {}).get("status") or lifecycle.get("status") or "").strip()
    if explicit:
        return explicit
    if phase == "started":
        return "started"
    if phase in {"input", "output"}:
        return "running"
    if phase == "completed":
        return "ok"
    return None


def _shell_stdin(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_stdin(payload)


def _shell_interaction_input(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_interaction_input(
        payload,
        shell_phase_fn=_shell_phase,
        shell_stdin_fn=_shell_stdin,
    )


def _shell_output_text(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_output_text(
        payload,
        shell_phase_fn=_shell_phase,
    )


def _shell_output_chunk(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_runtime_service.shell_output_chunk(
        payload,
        shell_phase_fn=_shell_phase,
    )


def _shell_stdout(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_stdout(payload)


def _shell_stderr(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_stderr(payload)


def _shell_aggregated_output(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_aggregated_output(
        payload,
        shell_stdout_fn=_shell_stdout,
        shell_stderr_fn=_shell_stderr,
    )


def _shell_event_source(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_event_source(payload, shell_phase_fn=_shell_phase)


def _shell_io_mode(payload: dict[str, Any] | None) -> str | None:
    return app_server_shell_protocol_helpers.shell_io_mode(payload)


def _shell_protocol_fields(
    payload: dict[str, Any] | None,
    *,
    session_id: str | None = None,
    command: str | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    return app_server_shell_protocol_runtime_service.shell_protocol_fields(
        payload,
        session_id=session_id,
        command=command,
        include_raw=include_raw,
        shell_output_chunk_fn=_shell_output_chunk,
        shell_lifecycle_dict_fn=_shell_lifecycle_dict,
        shell_phase_fn=_shell_phase,
        shell_event_kind_fn=_shell_event_kind,
        shell_call_id_fn=_shell_call_id,
        shell_process_id_fn=_shell_process_id,
        shell_command_text_fn=_shell_command_text,
        shell_cwd_fn=_shell_cwd,
        shell_event_source_fn=_shell_event_source,
        shell_status_fn=_shell_status,
        shell_io_mode_fn=_shell_io_mode,
        shell_stdin_fn=_shell_stdin,
        shell_interaction_input_fn=_shell_interaction_input,
        shell_output_text_fn=_shell_output_text,
    )


def _is_shell_execution_payload(payload: dict[str, Any] | None) -> bool:
    return app_server_shell_protocol_helpers.is_shell_execution_payload(payload)


def _command_response_shell_metadata(response: PromptResponse) -> dict[str, Any]:
    if not response.tool_events:
        return {}
    tool_event = response.tool_events[-1]
    if not _is_shell_execution_payload(tool_event.payload):
        return {}
    return {
        **_shell_protocol_fields(tool_event.payload, include_raw=True),
        "stdout": _shell_stdout(tool_event.payload),
        "stderr": _shell_stderr(tool_event.payload),
        "aggregatedOutput": _shell_aggregated_output(tool_event.payload),
    }


def _shell_activity_to_event(payload: dict[str, Any]) -> ActivityEvent | None:
    return app_server_shell_protocol_runtime_service.shell_activity_to_event(
        payload,
        shell_phase_fn=_shell_phase,
    )


def _shell_activity_to_turn_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    return app_server_shell_protocol_runtime_service.shell_activity_to_turn_event(
        payload,
        shell_phase_fn=_shell_phase,
        shell_turn_item_fn=_shell_turn_item,
        shell_status_fn=_shell_status,
        shell_interaction_input_fn=_shell_interaction_input,
        shell_output_text_fn=_shell_output_text,
        shell_stdout_fn=_shell_stdout,
        shell_stderr_fn=_shell_stderr,
    )


def _shell_turn_item(payload: dict[str, Any] | None) -> dict[str, Any]:
    return app_server_shell_protocol_runtime_service.shell_turn_item(
        payload,
        shell_call_id_fn=_shell_call_id,
        shell_command_text_fn=_shell_command_text,
    )


def _compose_command_turn_events(
    response: PromptResponse,
    *,
    item_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_item_events = [dict(item) for item in list(item_events or []) if isinstance(item, dict)]
    if not normalized_item_events:
        fallback_items, _ = tool_events_to_turn_events(list(response.tool_events or []), start_index=0)
        normalized_item_events = [dict(item) for item in list(fallback_items or []) if isinstance(item, dict)]
    fallback_turn_events = prompt_response_turn_events(response)
    turn_completed = (
        dict(next((item for item in reversed(fallback_turn_events) if item.get("type") == "turn.completed"), {}))
        or {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}}
    )
    return [
        {"type": "turn.started"},
        *normalized_item_events,
        turn_completed,
    ]


def _completed_shell_item_events(
    payload: dict[str, Any] | None,
    *,
    session_turn_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return app_server_shell_protocol_runtime_service.completed_shell_item_events(
        payload,
        session_turn_events=session_turn_events,
        shell_payload_item_events_fn=_shell_payload_item_events,
        shell_activity_to_turn_event_fn=_shell_activity_to_turn_event,
    )


def _shell_payload_item_events(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return app_server_shell_protocol_runtime_service.shell_payload_item_events(
        payload,
        shell_activity_to_turn_event_fn=_shell_activity_to_turn_event,
    )


def _first_text(params: dict[str, Any], *names: str) -> str:
    return app_server_shell_protocol_helpers.first_text(params, *names)


def _optional_bool_param(params: dict[str, Any], *names: str) -> bool | None:
    return app_server_shell_protocol_helpers.optional_bool_param(params, *names)


def _optional_int_param(params: dict[str, Any], *names: str) -> int | None:
    return app_server_shell_protocol_helpers.optional_int_param(params, *names)


def _shell_options_from_params(params: dict[str, Any], *, interactive: bool) -> dict[str, Any]:
    return app_server_shell_protocol_runtime_service.shell_options_from_params(
        params,
        interactive=interactive,
        first_text_fn=_first_text,
        optional_bool_param_fn=_optional_bool_param,
        optional_int_param_fn=_optional_int_param,
    )


def _exit_code_for_response(response: PromptResponse) -> int:
    return headless_wiring_runtime_service.exit_code_for_response(
        response,
        service=headless_runtime_service,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure,
    )
