from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, TextIO

from cli.agent_cli import headless_event_runtime as headless_event_runtime_service
from cli.agent_cli import headless_snapshot_runtime as headless_snapshot_runtime_service
from cli.agent_cli import (
    headless_stream_normalization_helpers_runtime as headless_stream_normalization_helpers_service,
)
from cli.agent_cli import (
    headless_stream_projection_helpers_runtime as headless_stream_projection_helpers_service,
)
from cli.agent_cli import (
    headless_stream_pure_helpers_runtime as headless_stream_pure_helpers_service,
)
from cli.agent_cli import (
    headless_stream_runtime_helpers as headless_stream_runtime_helpers_service,
)
from cli.agent_cli.models import (
    ActivityEvent,
    PromptResponse,
    ToolEvent,
)

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


def prompt_response_to_dict(
    response: PromptResponse,
    *,
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
    tool_event_to_dict_fn: Callable[[ToolEvent], dict[str, Any]],
    activity_event_to_dict_fn: Callable[[ActivityEvent], dict[str, Any]],
) -> dict[str, Any]:
    return headless_stream_runtime_helpers_service.prompt_response_to_dict(
        response,
        canonical_turn_events_fn=canonical_turn_events_fn,
        tool_event_to_dict_fn=tool_event_to_dict_fn,
        activity_event_to_dict_fn=activity_event_to_dict_fn,
    )


def execute_prompt(
    runner: AgentCliRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    jsonl: bool,
    request_id: str | None = None,
    codex_jsonl: bool = False,
    headless_thread_id_fn: Callable[[AgentCliRuntime], str],
    emit_reference_jsonl_event_fn: Callable[..., None],
    turn_event_signature_fn: Callable[[dict[str, Any]], str],
    turn_event_backfill_signature_fn: Callable[[dict[str, Any]], str],
    temporary_turn_event_callback_fn: Callable[[AgentCliRuntime, Any], Any],
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
) -> PromptResponse:
    if not jsonl:
        return runner.handle_prompt(prompt)

    return _stream_prompt_jsonl(
        runner,
        prompt,
        output_stream=output_stream,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        headless_thread_id_fn=headless_thread_id_fn,
        emit_reference_jsonl_event_fn=emit_reference_jsonl_event_fn,
        turn_event_signature_fn=turn_event_signature_fn,
        turn_event_backfill_signature_fn=turn_event_backfill_signature_fn,
        temporary_turn_event_callback_fn=temporary_turn_event_callback_fn,
        canonical_turn_events_fn=canonical_turn_events_fn,
    )


def _stream_prompt_jsonl(
    runner: AgentCliRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    request_id: str | None,
    codex_jsonl: bool,
    headless_thread_id_fn: Callable[[AgentCliRuntime], str],
    emit_reference_jsonl_event_fn: Callable[..., None],
    turn_event_signature_fn: Callable[[dict[str, Any]], str],
    turn_event_backfill_signature_fn: Callable[[dict[str, Any]], str],
    temporary_turn_event_callback_fn: Callable[[AgentCliRuntime, Any], Any],
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
) -> PromptResponse:
    return headless_stream_pure_helpers_service.stream_prompt_jsonl(
        runner,
        prompt,
        output_stream=output_stream,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        headless_thread_id_fn=headless_thread_id_fn,
        emit_reference_jsonl_event_fn=emit_reference_jsonl_event_fn,
        turn_event_signature_fn=turn_event_signature_fn,
        turn_event_backfill_signature_fn=turn_event_backfill_signature_fn,
        temporary_turn_event_callback_fn=temporary_turn_event_callback_fn,
        canonical_turn_events_fn=canonical_turn_events_fn,
    )


def canonical_turn_events(
    response: PromptResponse,
    *,
    response_items: list[Any] | None = None,
    shell_turn_events_from_tool_events_fn: Callable[[list[ToolEvent]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return headless_snapshot_runtime_service.canonical_turn_events(
        response,
        response_items=response_items,
        shell_turn_events_from_tool_events_fn=shell_turn_events_from_tool_events_fn,
    )


def shell_turn_events_from_tool_events(
    tool_events: list[ToolEvent],
    *,
    shell_item_events_from_payload_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return headless_event_runtime_service.shell_turn_events_from_tool_events(
        tool_events,
        shell_item_events_from_payload_fn=shell_item_events_from_payload_fn,
    )


def shell_item_events_from_payload(
    payload: dict[str, Any],
    *,
    shell_activity_to_turn_event_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    return headless_event_runtime_service.shell_item_events_from_payload(
        payload,
        shell_activity_to_turn_event_fn=shell_activity_to_turn_event_fn,
    )


def shell_activity_to_turn_event(
    payload: dict[str, Any],
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str],
    shell_turn_item_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    shell_status_fn: Callable[[dict[str, Any] | None], str],
    shell_interaction_input_fn: Callable[[dict[str, Any] | None], str | None],
    shell_output_text_fn: Callable[[dict[str, Any] | None], str | None],
) -> dict[str, Any] | None:
    return headless_event_runtime_service.shell_activity_to_turn_event(
        payload,
        shell_phase_fn=shell_phase_fn,
        shell_turn_item_fn=shell_turn_item_fn,
        shell_status_fn=shell_status_fn,
        shell_interaction_input_fn=shell_interaction_input_fn,
        shell_output_text_fn=shell_output_text_fn,
    )


def shell_phase(payload: dict[str, Any] | None) -> str:
    return headless_event_runtime_service.shell_phase(payload)


def shell_status(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str],
) -> str:
    return headless_event_runtime_service.shell_status(payload, shell_phase_fn=shell_phase_fn)


def shell_interaction_input(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str],
) -> str | None:
    return headless_event_runtime_service.shell_interaction_input(
        payload, shell_phase_fn=shell_phase_fn
    )


def shell_output_text(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str],
) -> str | None:
    return headless_event_runtime_service.shell_output_text(payload, shell_phase_fn=shell_phase_fn)


def shell_turn_item(
    payload: dict[str, Any] | None,
    *,
    shell_call_id_fn: Callable[[dict[str, Any] | None], str],
) -> dict[str, Any]:
    return headless_event_runtime_service.shell_turn_item(
        payload, shell_call_id_fn=shell_call_id_fn
    )


def shell_call_id(payload: dict[str, Any] | None) -> str:
    return headless_event_runtime_service.shell_call_id(payload)


def headless_thread_id(runner: AgentCliRuntime) -> str:
    return headless_stream_normalization_helpers_service.headless_thread_id(runner)


def run_serve_loop(
    runner: AgentCliRuntime,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    emit_json_line_fn: Callable[[TextIO, dict[str, Any]], None],
    request_id_for_payload_fn: Callable[[Any], str | None],
    resolve_serve_prompt_fn: Callable[[Any], str],
    execute_prompt_fn: Callable[..., PromptResponse],
    prompt_response_to_dict_fn: Callable[[PromptResponse], dict[str, Any]],
    exit_code_for_response_fn: Callable[[PromptResponse], int],
) -> int:
    return headless_stream_runtime_helpers_service.run_serve_loop(
        runner,
        input_stream=input_stream,
        output_stream=output_stream,
        emit_json_line_fn=emit_json_line_fn,
        request_id_for_payload_fn=request_id_for_payload_fn,
        resolve_serve_prompt_fn=resolve_serve_prompt_fn,
        execute_prompt_fn=execute_prompt_fn,
        prompt_response_to_dict_fn=prompt_response_to_dict_fn,
        exit_code_for_response_fn=exit_code_for_response_fn,
    )


def request_id_for_payload(payload: Any) -> str | None:
    return headless_stream_normalization_helpers_service.request_id_for_payload(payload)


def resolve_serve_prompt(payload: Any) -> str:
    return headless_stream_normalization_helpers_service.resolve_serve_prompt(payload)


def tool_event_to_dict(item: ToolEvent) -> dict[str, Any]:
    return headless_stream_projection_helpers_service.tool_event_to_dict(item)


def activity_event_to_dict(item: ActivityEvent) -> dict[str, Any]:
    return headless_stream_projection_helpers_service.activity_event_to_dict(item)


def emit_json_line(output_stream: TextIO, payload: dict[str, Any]) -> None:
    return headless_stream_projection_helpers_service.emit_json_line(output_stream, payload)


def emit_reference_jsonl_event(
    output_stream: TextIO,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    codex_jsonl: bool = False,
    emit_json_line_fn: Callable[[TextIO, dict[str, Any]], None],
) -> None:
    return headless_stream_projection_helpers_service.emit_reference_jsonl_event(
        output_stream,
        payload,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        emit_json_line_fn=emit_json_line_fn,
    )


def stream_json_event_type(payload: dict[str, Any]) -> str:
    return headless_stream_projection_helpers_service.stream_json_event_type(payload)


def turn_event_signature(event: dict[str, Any]) -> str:
    return headless_stream_pure_helpers_service.turn_event_signature(event)


def normalized_turn_event_value(value: Any) -> Any:
    return headless_snapshot_runtime_service.normalized_turn_event_value(value)


def turn_event_backfill_signature(
    event: dict[str, Any],
    *,
    normalized_turn_event_value_fn: Callable[[Any], Any],
) -> str:
    return headless_snapshot_runtime_service.turn_event_backfill_signature(
        event,
        normalized_turn_event_value_fn=normalized_turn_event_value_fn,
    )


def temporary_activity_callback(
    runner: AgentCliRuntime,
    callback: Any,
) -> Iterator[None]:
    return headless_stream_pure_helpers_service.temporary_activity_callback(runner, callback)


def temporary_turn_event_callback(
    runner: AgentCliRuntime,
    callback: Any,
) -> Iterator[None]:
    return headless_stream_pure_helpers_service.temporary_turn_event_callback(runner, callback)
