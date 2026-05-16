from __future__ import annotations

from typing import TYPE_CHECKING, Any, TextIO

from cli.agent_cli import headless_runtime as headless_runtime_service
from cli.agent_cli import (
    headless_shell_projection_runtime as headless_shell_projection_runtime_service,
)
from cli.agent_cli import headless_stream_runtime as headless_stream_runtime_service
from cli.agent_cli import headless_wiring_runtime as headless_wiring_runtime_service
from cli.agent_cli.models import (
    PromptResponse,
    response_items_to_text,
    tool_event_is_soft_failure,
)

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter import (
        CodexSidecarRuntimeAdapter,
    )

    HeadlessRuntime = AgentCliRuntime | CodexSidecarRuntimeAdapter
else:
    HeadlessRuntime = Any


def prompt_response_to_dict(response: PromptResponse) -> dict[str, Any]:
    return prompt_response_to_dict_with_hooks(
        response,
        canonical_turn_events_fn=canonical_turn_events,
        tool_event_to_dict_fn=tool_event_to_dict,
        activity_event_to_dict_fn=activity_event_to_dict,
    )


def prompt_response_to_dict_with_hooks(
    response: PromptResponse,
    *,
    canonical_turn_events_fn: Any,
    tool_event_to_dict_fn: Any,
    activity_event_to_dict_fn: Any,
) -> dict[str, Any]:
    return headless_wiring_runtime_service.prompt_response_to_dict(
        response,
        service=headless_stream_runtime_service,
        canonical_turn_events_fn=canonical_turn_events_fn,
        tool_event_to_dict_fn=tool_event_to_dict_fn,
        activity_event_to_dict_fn=activity_event_to_dict_fn,
    )


def execute_prompt(
    runner: HeadlessRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    jsonl: bool,
    request_id: str | None = None,
    codex_jsonl: bool = False,
    headless_thread_id_fn: Any = None,
    emit_reference_jsonl_event_fn: Any = None,
    turn_event_signature_fn: Any = None,
    turn_event_backfill_signature_fn: Any = None,
    temporary_turn_event_callback_fn: Any = None,
    canonical_turn_events_fn: Any = None,
) -> PromptResponse:
    return headless_wiring_runtime_service.execute_prompt(
        runner,
        prompt,
        output_stream=output_stream,
        jsonl=jsonl,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        service=headless_stream_runtime_service,
        headless_thread_id_fn=headless_thread_id_fn or headless_thread_id,
        emit_reference_jsonl_event_fn=emit_reference_jsonl_event_fn or emit_reference_jsonl_event,
        turn_event_signature_fn=turn_event_signature_fn or turn_event_signature,
        turn_event_backfill_signature_fn=(
            turn_event_backfill_signature_fn or turn_event_backfill_signature
        ),
        temporary_turn_event_callback_fn=(
            temporary_turn_event_callback_fn or temporary_turn_event_callback
        ),
        canonical_turn_events_fn=canonical_turn_events_fn or canonical_turn_events,
    )


def run_serve_loop(
    runner: HeadlessRuntime,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    emit_json_line_fn: Any = None,
    request_id_for_payload_fn: Any = None,
    resolve_serve_prompt_fn: Any = None,
    execute_prompt_fn: Any = None,
    prompt_response_to_dict_fn: Any = None,
    exit_code_for_response_fn: Any = None,
) -> int:
    return headless_wiring_runtime_service.run_serve_loop(
        runner,
        input_stream=input_stream,
        output_stream=output_stream,
        service=headless_stream_runtime_service,
        emit_json_line_fn=emit_json_line_fn or emit_json_line,
        request_id_for_payload_fn=request_id_for_payload_fn or request_id_for_payload,
        resolve_serve_prompt_fn=resolve_serve_prompt_fn or resolve_serve_prompt,
        execute_prompt_fn=execute_prompt_fn or execute_prompt,
        prompt_response_to_dict_fn=prompt_response_to_dict_fn or prompt_response_to_dict,
        exit_code_for_response_fn=exit_code_for_response_fn or exit_code_for_response,
    )


def render_text_output(response: PromptResponse) -> str:
    from cli.agent_cli.runtime_core.command_dispatch import tool_result_fallback_text

    return headless_wiring_runtime_service.render_text_output(
        response,
        service=headless_runtime_service,
        response_items_to_text_fn=response_items_to_text,
        tool_result_fallback_text_fn=tool_result_fallback_text,
    )


def exit_code_for_response(response: PromptResponse) -> int:
    return headless_wiring_runtime_service.exit_code_for_response(
        response,
        service=headless_runtime_service,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure,
    )


def emit_reference_jsonl_event(
    output_stream: TextIO,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    codex_jsonl: bool = False,
    emit_json_line_fn: Any = None,
) -> None:
    headless_stream_runtime_service.emit_reference_jsonl_event(
        output_stream,
        payload,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        emit_json_line_fn=emit_json_line_fn or emit_json_line,
    )


def turn_event_backfill_signature(
    event: dict[str, Any],
    *,
    normalized_turn_event_value_fn: Any = None,
) -> str:
    return headless_wiring_runtime_service.turn_event_backfill_signature(
        event,
        service=headless_stream_runtime_service,
        normalized_turn_event_value_fn=(
            normalized_turn_event_value_fn or normalized_turn_event_value
        ),
    )


def temporary_activity_callback(
    runner: HeadlessRuntime,
    callback: Any,
) -> Any:
    return headless_stream_runtime_service.temporary_activity_callback(runner, callback)


def temporary_turn_event_callback(
    runner: HeadlessRuntime,
    callback: Any,
) -> Any:
    return headless_stream_runtime_service.temporary_turn_event_callback(runner, callback)


headless_thread_id = headless_stream_runtime_service.headless_thread_id
request_id_for_payload = headless_stream_runtime_service.request_id_for_payload
resolve_serve_prompt = headless_stream_runtime_service.resolve_serve_prompt
tool_event_to_dict = headless_stream_runtime_service.tool_event_to_dict
activity_event_to_dict = headless_stream_runtime_service.activity_event_to_dict
has_piped_input = headless_runtime_service.has_piped_input
emit_json_line = headless_stream_runtime_service.emit_json_line
turn_event_signature = headless_stream_runtime_service.turn_event_signature
normalized_turn_event_value = headless_stream_runtime_service.normalized_turn_event_value
canonical_turn_events = headless_shell_projection_runtime_service.canonical_turn_events
shell_turn_events_from_tool_events = (
    headless_shell_projection_runtime_service.shell_turn_events_from_tool_events
)
shell_item_events_from_payload = (
    headless_shell_projection_runtime_service.shell_item_events_from_payload
)
shell_activity_to_turn_event = (
    headless_shell_projection_runtime_service.shell_activity_to_turn_event
)
shell_phase = headless_shell_projection_runtime_service.shell_phase
shell_status = headless_shell_projection_runtime_service.shell_status
shell_interaction_input = headless_shell_projection_runtime_service.shell_interaction_input
shell_output_text = headless_shell_projection_runtime_service.shell_output_text
shell_turn_item = headless_shell_projection_runtime_service.shell_turn_item
shell_call_id = headless_shell_projection_runtime_service.shell_call_id
