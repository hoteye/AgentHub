from __future__ import annotations

from collections.abc import Callable
from typing import Any, TextIO


def prompt_response_to_dict(
    response: Any,
    *,
    service: Any,
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
    tool_event_to_dict_fn: Callable[[Any], dict[str, Any]],
    activity_event_to_dict_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    return service.prompt_response_to_dict(
        response,
        canonical_turn_events_fn=canonical_turn_events_fn,
        tool_event_to_dict_fn=tool_event_to_dict_fn,
        activity_event_to_dict_fn=activity_event_to_dict_fn,
    )


def configure_runtime_for_policy(runner: Any, *, runtime_policy: Any) -> None:
    configure = getattr(runner, "configure_runtime_policy", None)
    if not callable(configure):
        return
    configure(
        approval_policy=runtime_policy.approval_policy,
        sandbox_mode=runtime_policy.sandbox_mode,
        web_search_mode=runtime_policy.web_search_mode,
        network_access_enabled=runtime_policy.network_access_enabled,
    )


def execute_prompt(
    runner: Any,
    prompt: str,
    *,
    output_stream: TextIO,
    jsonl: bool,
    request_id: str | None,
    codex_jsonl: bool = False,
    service: Any,
    headless_thread_id_fn: Callable[[Any], str],
    emit_reference_jsonl_event_fn: Callable[..., None],
    turn_event_signature_fn: Callable[[dict[str, Any]], str],
    turn_event_backfill_signature_fn: Callable[[dict[str, Any]], str],
    temporary_turn_event_callback_fn: Callable[[Any, Any], Any],
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
) -> Any:
    return service.execute_prompt(
        runner,
        prompt,
        output_stream=output_stream,
        jsonl=jsonl,
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
    response: Any,
    *,
    response_items: list[Any] | None,
    service: Any,
    shell_turn_events_from_tool_events_fn: Callable[[list[Any]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return service.canonical_turn_events(
        response,
        response_items=response_items,
        shell_turn_events_from_tool_events_fn=shell_turn_events_from_tool_events_fn,
    )


def shell_turn_events_from_tool_events(
    tool_events: list[Any],
    *,
    service: Any,
    shell_item_events_from_payload_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return service.shell_turn_events_from_tool_events(
        tool_events,
        shell_item_events_from_payload_fn=shell_item_events_from_payload_fn,
    )


def shell_item_events_from_payload(
    payload: dict[str, Any],
    *,
    service: Any,
    shell_activity_to_turn_event_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    return service.shell_item_events_from_payload(
        payload,
        shell_activity_to_turn_event_fn=shell_activity_to_turn_event_fn,
    )


def shell_activity_to_turn_event(
    payload: dict[str, Any],
    *,
    service: Any,
    shell_phase_fn: Callable[[dict[str, Any] | None], str],
    shell_turn_item_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    shell_status_fn: Callable[[dict[str, Any] | None], str],
    shell_interaction_input_fn: Callable[[dict[str, Any] | None], str | None],
    shell_output_text_fn: Callable[[dict[str, Any] | None], str | None],
) -> dict[str, Any] | None:
    return service.shell_activity_to_turn_event(
        payload,
        shell_phase_fn=shell_phase_fn,
        shell_turn_item_fn=shell_turn_item_fn,
        shell_status_fn=shell_status_fn,
        shell_interaction_input_fn=shell_interaction_input_fn,
        shell_output_text_fn=shell_output_text_fn,
    )


def run_serve_loop(
    runner: Any,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    service: Any,
    emit_json_line_fn: Callable[[TextIO, dict[str, Any]], None],
    request_id_for_payload_fn: Callable[[Any], str | None],
    resolve_serve_prompt_fn: Callable[[Any], str],
    execute_prompt_fn: Callable[..., Any],
    prompt_response_to_dict_fn: Callable[[Any], dict[str, Any]],
    exit_code_for_response_fn: Callable[[Any], int],
) -> int:
    return service.run_serve_loop(
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


def render_text_output(
    response: Any,
    *,
    service: Any,
    response_items_to_text_fn: Callable[..., str],
    tool_result_fallback_text_fn: Callable[..., str],
) -> str:
    return service.render_text_output(
        response,
        response_items_to_text_fn=response_items_to_text_fn,
        tool_result_fallback_text_fn=tool_result_fallback_text_fn,
    )


def exit_code_for_response(
    response: Any,
    *,
    service: Any,
    tool_event_is_soft_failure_fn: Callable[[Any], bool],
) -> int:
    return service.exit_code_for_response(
        response,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure_fn,
    )


def turn_event_backfill_signature(
    event: dict[str, Any],
    *,
    service: Any,
    normalized_turn_event_value_fn: Callable[[Any], Any],
) -> str:
    return service.turn_event_backfill_signature(
        event,
        normalized_turn_event_value_fn=normalized_turn_event_value_fn,
    )
