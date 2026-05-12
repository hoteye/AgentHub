from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import (
    AgentIntent,
    PromptAttachment,
    ToolEvent,
    default_response_items,
    response_items_to_text,
)
from cli.agent_cli.providers.planner_postprocessing import (
    sanitize_final_answer_text,
    structured_tool_fallback_text,
)

PlannerToolExecutor = Callable[[str], tuple[str, list[ToolEvent]]]


def plan(
    planner: Any,
    user_text: str,
    history: list[dict[str, str]],
    *,
    tool_executor: PlannerToolExecutor | None = None,
    attachments: list[PromptAttachment] | None = None,
    input_items: list[dict[str, Any]] | None = None,
    prompt_cache_key: str | None = None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
    responses_session_cls: Callable[..., Any],
    turn_engine_cls: Callable[..., Any],
) -> AgentIntent:
    if tool_executor is None:
        return planner._plan_without_native_tools(
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )

    messages = planner._conversation_input_items(
        user_text,
        planner._history_for_conversation(history, input_items=input_items),
        attachments=attachments,
        input_items=input_items,
    )

    session = responses_session_cls(
        client=planner.client,
        model=planner.config.model,
        instructions=planner.native_tool_system_prompt,
        tool_specs=planner._tool_specs(),
        reasoning_effort=planner.config.reasoning_effort,
        prompt_cache_key=str(prompt_cache_key or "").strip() or None,
    )

    def _followup_handler(
        followup_user_text: str,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        continuation_input_items: list[dict[str, Any]] | None = None,
    ) -> AgentIntent:
        if continuation_input_items:
            try:
                return planner._resume_native_tool_followup(
                    session=session,
                    user_text=followup_user_text,
                    tool_executor=tool_executor,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                    previous_response_id=previous_response_id,
                    continuation_input_items=continuation_input_items,
                    terminal_handler=_terminal_handler,
                )
            except Exception:
                return _terminal_handler(
                    followup_user_text,
                    executed_events,
                    executed_item_events,
                    previous_response_id,
                    continuation_input_items,
                )
        try:
            return planner._fresh_followup_after_tool_loop(
                user_text=followup_user_text,
                executed_events=executed_events,
                tool_executor=tool_executor,
                executed_item_events=executed_item_events,
                attachments=attachments,
            )
        except Exception:
            return _terminal_handler(
                followup_user_text,
                executed_events,
                executed_item_events,
                previous_response_id,
                continuation_input_items,
            )

    def _terminal_handler(
        followup_user_text: str,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]] | None = None,
        _previous_response_id: str | None = None,
        _continuation_input_items: list[dict[str, Any]] | None = None,
    ) -> AgentIntent:
        try:
            return planner._fresh_synthesis_after_tool_loop(
                user_text=followup_user_text,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
                attachments=attachments,
            )
        except Exception:
            response_items = default_response_items(
                assistant_text=structured_tool_fallback_text(executed_events) or "模型未返回内容。"
            )
            return AgentIntent(
                assistant_text=response_items_to_text(response_items),
                response_items=response_items,
                command_text=None,
                status_hint="tool",
                tool_events=list(executed_events),
                turn_events=planner._compose_turn_events(
                    assistant_text=response_items_to_text(response_items),
                    response_items=response_items,
                    executed_item_events=list(executed_item_events or []),
                ),
            )

    engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=_followup_handler,
        terminal_handler=_terminal_handler,
        turn_event_callback=turn_event_callback,
    )
    raw_intent = engine.run(
        user_text=user_text,
        initial_input=messages,
        prompt_cache_key=str(prompt_cache_key or "").strip() or None,
    )
    response_items_list = list(raw_intent.response_items or [])
    response_items_text = response_items_to_text(response_items_list)
    assistant_text = sanitize_final_answer_text(str(raw_intent.assistant_text or "").strip())
    if not assistant_text and response_items_list:
        assistant_text = sanitize_final_answer_text(response_items_text)
    final_response_items = list(response_items_list)
    turn_events = [
        dict(item) for item in list(raw_intent.turn_events or []) if isinstance(item, dict)
    ]
    tool_item_events = planner._tool_item_events_from_turn_events(turn_events)
    response_has_text = bool(response_items_text.strip())
    needs_synthesis = (
        not assistant_text
        and raw_intent.tool_events
        and not (tool_item_events and response_has_text)
    )
    if needs_synthesis:
        try:
            synthesized = planner._fresh_synthesis_after_tool_loop(
                user_text=user_text,
                executed_events=list(raw_intent.tool_events or []),
                executed_item_events=tool_item_events,
                attachments=attachments,
            )
            synthesized_text = sanitize_final_answer_text(
                str(synthesized.assistant_text or "").strip()
            )
            if not synthesized_text and synthesized.response_items:
                synthesized_text = sanitize_final_answer_text(
                    response_items_to_text(list(synthesized.response_items or []))
                )
            if synthesized_text:
                assistant_text = synthesized_text
                response_items = list(
                    synthesized.response_items
                    or default_response_items(assistant_text=assistant_text)
                )
                final_response_items = response_items
                if synthesized.turn_events:
                    turn_events = [
                        dict(item)
                        for item in list(synthesized.turn_events or [])
                        if isinstance(item, dict)
                    ]
        except Exception:
            pass
    elif not assistant_text and tool_item_events:
        assistant_text = (
            structured_tool_fallback_text(raw_intent.tool_events)
            if raw_intent.tool_events
            else assistant_text
        )
    if not assistant_text:
        assistant_text = (
            structured_tool_fallback_text(raw_intent.tool_events)
            if raw_intent.tool_events
            else "模型未返回内容。"
        )
    if not final_response_items:
        final_response_items = list(default_response_items(assistant_text=assistant_text))

    return AgentIntent(
        assistant_text=assistant_text,
        response_items=list(final_response_items),
        command_text=None,
        status_hint="tool" if raw_intent.tool_events else "llm",
        tool_events=raw_intent.tool_events,
        turn_events=planner._canonical_turn_events(
            assistant_text=assistant_text,
            response_items=list(final_response_items),
            executed_item_events=tool_item_events,
            existing_turn_events=turn_events,
        ),
        timings=dict(raw_intent.timings or {}),
    )


def plan_without_native_tools(
    planner: Any,
    user_text: str,
    history: list[dict[str, str]],
    *,
    attachments: list[PromptAttachment] | None = None,
    input_items: list[dict[str, Any]] | None = None,
) -> AgentIntent:
    started_at = time.perf_counter()
    messages = planner._conversation_input_items(
        user_text,
        planner._history_for_conversation(history, input_items=input_items),
        attachments=attachments,
        input_items=input_items,
    )
    kwargs: dict[str, Any] = {
        "model": planner.config.model,
        "instructions": planner.system_prompt,
        "input": messages,
        "store": False,
        "stream": True,
    }
    reasoning = planner._reasoning_request()
    if reasoning:
        kwargs["reasoning"] = reasoning
    initial_started_at = time.perf_counter()
    raw_text = planner._collect_stream_text(**kwargs)
    initial_model_ms = int((time.perf_counter() - initial_started_at) * 1000)
    intent = planner._intent_from_raw_text(raw_text)
    intent.timings = {
        "initial_model_ms": initial_model_ms,
        "tool_execution_ms": 0,
        "synthesis_model_ms": 0,
        "total_ms": int((time.perf_counter() - started_at) * 1000),
        "planning_rounds": 1,
        "synthesis_rounds": 0,
        "tool_call_count": 0,
    }
    return intent
