from __future__ import annotations

from typing import Any

from cli.agent_cli import headless_stream_runtime as headless_stream_runtime_service
from cli.agent_cli import headless_wiring_runtime as headless_wiring_runtime_service


def canonical_turn_events(
    response: Any,
    *,
    response_items: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return headless_wiring_runtime_service.canonical_turn_events(
        response,
        response_items=response_items,
        service=headless_stream_runtime_service,
        shell_turn_events_from_tool_events_fn=shell_turn_events_from_tool_events,
    )


def shell_turn_events_from_tool_events(tool_events: list[Any]) -> list[dict[str, Any]]:
    return headless_wiring_runtime_service.shell_turn_events_from_tool_events(
        tool_events,
        service=headless_stream_runtime_service,
        shell_item_events_from_payload_fn=shell_item_events_from_payload,
    )


def shell_item_events_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return headless_wiring_runtime_service.shell_item_events_from_payload(
        payload,
        service=headless_stream_runtime_service,
        shell_activity_to_turn_event_fn=shell_activity_to_turn_event,
    )


def shell_activity_to_turn_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    return headless_wiring_runtime_service.shell_activity_to_turn_event(
        payload,
        service=headless_stream_runtime_service,
        shell_phase_fn=shell_phase,
        shell_turn_item_fn=shell_turn_item,
        shell_status_fn=shell_status,
        shell_interaction_input_fn=shell_interaction_input,
        shell_output_text_fn=shell_output_text,
    )


def shell_phase(payload: dict[str, Any] | None) -> str:
    return headless_stream_runtime_service.shell_phase(payload)


def shell_status(payload: dict[str, Any] | None) -> str:
    return headless_stream_runtime_service.shell_status(payload, shell_phase_fn=shell_phase)


def shell_interaction_input(payload: dict[str, Any] | None) -> str | None:
    return headless_stream_runtime_service.shell_interaction_input(
        payload,
        shell_phase_fn=shell_phase,
    )


def shell_output_text(payload: dict[str, Any] | None) -> str | None:
    return headless_stream_runtime_service.shell_output_text(
        payload,
        shell_phase_fn=shell_phase,
    )


def shell_turn_item(payload: dict[str, Any] | None) -> dict[str, Any]:
    return headless_stream_runtime_service.shell_turn_item(payload, shell_call_id_fn=shell_call_id)


def shell_call_id(payload: dict[str, Any] | None) -> str:
    return headless_stream_runtime_service.shell_call_id(payload)
