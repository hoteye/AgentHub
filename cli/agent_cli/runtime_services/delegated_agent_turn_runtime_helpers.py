from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services import (
    delegated_agent_turn_result_runtime as delegated_agent_turn_result_runtime_service,
)


def _noop_turn_event_callback(_event: dict[str, Any]) -> None:
    """Keep delegated child requests on the streaming code path without surfacing UI events."""


def delegated_plan_kwargs_impl(
    runtime: Any,
    planner: Any,
    *,
    session: Any,
) -> dict[str, Any]:
    current_input_items = []
    active_input = getattr(session, "active_input", None)
    if isinstance(active_input, dict):
        current_input_items = [
            dict(item)
            for item in list(active_input.get("input_items") or [])
            if isinstance(item, dict)
        ]
    subagent_type = str(getattr(session, "subagent_type", "") or "").strip()
    profile_items = builtin_agent_profiles_runtime.profile_instruction_items(subagent_type)
    tool_executor = builtin_agent_profiles_runtime.profiled_tool_executor(
        runtime._structured_tool_executor,
        subagent_type=subagent_type,
    )
    plan_kwargs = runtime._filter_handler_kwargs(
        planner.plan,
        {
            "history": [
                dict(item)
                for item in [
                    *list(session.seed_history or []),
                    *list(session.replay_history or []),
                ]
                if isinstance(item, dict)
            ],
            "tool_executor": tool_executor,
            "attachments": [],
            "input_items": [
                dict(item)
                for item in [
                    *list(profile_items or []),
                    *list(session.seed_input_items or []),
                    *list(session.replay_input_items or []),
                    *list(current_input_items or []),
                ]
                if isinstance(item, dict)
            ],
            "prompt_cache_key": (
                f"{runtime.thread_id or 'adhoc'}:delegate:{session.agent_id}:{session.turn_count + 1}"
            ),
            "subagent_type": subagent_type,
            # OpenAI Responses request assembly derives stream=true from the presence of
            # turn_event_callback. Delegated workers suppress direct callback emission at the
            # runtime boundary, but they still need the streaming transport path.
            "turn_event_callback": _noop_turn_event_callback,
        },
    )
    if "input_items" in plan_kwargs and "history" in plan_kwargs:
        plan_kwargs["history"] = []
    return plan_kwargs


def apply_delegated_turn_result_impl(
    runtime: Any,
    session: Any,
    *,
    user_text: str,
    step_id: str,
    result: CommandExecutionResult,
    preview_text_fn: Callable[[Any], str],
) -> None:
    assistant_text = delegated_agent_turn_result_runtime_service.populate_session_from_result(
        runtime,
        session,
        result,
        user_text,
        include_assistant_history=True,
    )
    if step_id:
        delegated_agent_turn_result_runtime_service.record_delegated_step(
            runtime,
            session,
            step_id=step_id,
            status="completed",
            summary=preview_text_fn(assistant_text or "completed"),
            assistant_text=assistant_text,
            finished=True,
        )
    runtime._refresh_delegated_current_step_id(session)


def apply_interrupted_delegated_turn_result_impl(
    runtime: Any,
    session: Any,
    *,
    user_text: str,
    step_id: str,
    result: CommandExecutionResult,
    preserve_terminal_reason_fn: Callable[[Any, str], str],
) -> None:
    previous_terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip()
    delegated_agent_turn_result_runtime_service.populate_session_from_result(
        runtime,
        session,
        result,
        user_text,
        include_assistant_history=False,
        include_turn_history=False,
    )
    if session.close_requested:
        session.terminal_reason = previous_terminal_reason or preserve_terminal_reason_fn(
            session, "close_requested"
        )
    else:
        session.terminal_reason = ""
    if session.close_requested:
        session.assistant_text = ""
    if step_id:
        delegated_agent_turn_result_runtime_service.record_delegated_step(
            runtime,
            session,
            step_id=step_id,
            status="cancelled",
            summary="cancelled",
            finished=True,
        )
    runtime._refresh_delegated_current_step_id(session)
