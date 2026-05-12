from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import models_event_runtime as models_event_runtime_service
from cli.agent_cli import models_thread_serialization as models_thread_serialization_service


def thread_history_turn_from_dict(
    payload: dict[str, Any],
    *,
    prompt_attachment_from_dict_fn: Callable[[dict[str, Any]], Any],
    tool_event_from_dict_fn: Callable[[dict[str, Any]], Any],
    activity_event_from_dict_fn: Callable[[dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    return models_thread_serialization_service.thread_history_turn_from_dict(
        payload,
        prompt_attachment_from_dict_fn=prompt_attachment_from_dict_fn,
        tool_event_from_dict_fn=tool_event_from_dict_fn,
        activity_event_from_dict_fn=activity_event_from_dict_fn,
        reference_context_item_from_dict_fn=reference_context_item_from_dict_fn,
        response_input_item_from_dict_fn=response_input_item_from_dict_fn,
    )


def function_call_output_payload_body(
    output: Any,
    *,
    item_from_dict_fn: Callable[[dict[str, Any]], Any],
    item_from_text_fn: Callable[[str], Any],
) -> Any:
    return models_event_runtime_service.build_function_call_output_body(
        output,
        item_from_dict=item_from_dict_fn,
        item_from_text=item_from_text_fn,
    )


def function_call_output_payload_wire_value(
    body: Any,
    *,
    item_to_dict_fn: Callable[[Any], dict[str, Any]],
) -> Any:
    return models_event_runtime_service.wire_value_from_function_output_body(
        body,
        item_to_dict=item_to_dict_fn,
    )


def turn_context_input_item_from_dict(
    payload: dict[str, Any],
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    entry = models_thread_serialization_service.turn_context_input_item_from_dict(payload)
    return {
        "source": entry["source"],
        "item": response_input_item_from_dict_fn(entry["item_payload"]),
    }


def turn_context_rollout_from_dict(
    payload: dict[str, Any],
    *,
    turn_context_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    return models_thread_serialization_service.turn_context_rollout_from_dict(
        payload,
        turn_context_input_item_from_dict_fn=turn_context_input_item_from_dict_fn,
        reference_context_item_from_dict_fn=reference_context_item_from_dict_fn,
    )


def rollout_item_from_dict(
    payload: dict[str, Any],
    *,
    thread_history_turn_from_dict_fn: Callable[[dict[str, Any]], Any],
    thread_history_turn_from_legacy_turn_payload_fn: Callable[[dict[str, Any]], Any],
    turn_context_rollout_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    return models_thread_serialization_service.rollout_item_from_dict(
        payload,
        thread_history_turn_from_dict_fn=thread_history_turn_from_dict_fn,
        thread_history_turn_from_legacy_turn_payload_fn=thread_history_turn_from_legacy_turn_payload_fn,
        turn_context_rollout_from_dict_fn=turn_context_rollout_from_dict_fn,
    )
