from __future__ import annotations

from typing import Any

from cli.agent_cli.models import PromptResponse


def reference_context_items_from_response(
    response: PromptResponse,
    *,
    reference_context_items_from_tool_event_fn: Any,
    dedupe_reference_context_items_fn: Any,
) -> list[Any]:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.reference_context_items_from_response(
        response,
        reference_context_items_from_tool_event_fn=reference_context_items_from_tool_event_fn,
        dedupe_reference_context_items_fn=dedupe_reference_context_items_fn,
    )


def planner_history_from_turns(
    turns: list[Any],
    *,
    fallback_history: list[dict[str, str]] | None,
    planner_history_limit: int,
) -> list[dict[str, str]]:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.planner_history_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
    )


def planner_input_items_from_history(
    history: list[dict[str, str]],
    *,
    planner_history_limit: int,
) -> list[dict[str, Any]]:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.planner_input_items_from_history(
        history,
        planner_history_limit=planner_history_limit,
    )


def planner_input_items_from_turns(
    turns: list[Any],
    *,
    fallback_history: list[dict[str, str]] | None,
    planner_history_limit: int,
    turn_used_provider_fn: Any,
) -> list[dict[str, Any]]:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.planner_input_items_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=turn_used_provider_fn,
    )


def planner_input_items_from_rollout_items(
    rollout_items: list[dict[str, Any]],
    *,
    fallback_history: list[dict[str, str]] | None,
    planner_history_limit: int,
    turn_used_provider_fn: Any,
) -> list[dict[str, Any]]:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.planner_input_items_from_rollout_items(
        rollout_items,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=turn_used_provider_fn,
    )


def turn_used_provider(turn: Any, *, turn_has_structured_tool_items_fn: Any) -> bool:
    from cli.agent_cli import thread_store_helpers_runtime as helper_runtime

    return helper_runtime.turn_used_provider(
        turn,
        turn_has_structured_tool_items_fn=turn_has_structured_tool_items_fn,
    )


def history_turn_from_response(
    response: PromptResponse,
    *,
    timestamp: str,
    assistant_history_text: str,
    runtime_state: dict[str, Any] | None,
    canonical_turn_events_fn: Any,
    reference_context_items_from_tool_event_fn: Any,
    dedupe_reference_context_items_fn: Any,
    attachment_to_dict_fn: Any,
    tool_event_to_dict_fn: Any,
    activity_event_to_dict_fn: Any,
) -> Any:
    from cli.agent_cli import thread_store_runtime as thread_store_runtime_service

    return thread_store_runtime_service.history_turn_from_response(
        response,
        timestamp=timestamp,
        assistant_history_text=assistant_history_text,
        runtime_state=runtime_state,
        canonical_turn_events_fn=canonical_turn_events_fn,
        reference_context_items_from_tool_event_fn=reference_context_items_from_tool_event_fn,
        dedupe_reference_context_items_fn=dedupe_reference_context_items_fn,
        attachment_to_dict_fn=attachment_to_dict_fn,
        tool_event_to_dict_fn=tool_event_to_dict_fn,
        activity_event_to_dict_fn=activity_event_to_dict_fn,
    )
