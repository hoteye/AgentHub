from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import (
    AgentIntent,
    latest_open_todo_list_item,
    PromptAttachment,
    ToolEvent,
    default_response_items,
    response_items_to_text,
    todo_list_turn_event_from_plan_payload,
)
from cli.agent_cli.providers.adapters.openai_responses import extract_responses_message_items
from cli.agent_cli.providers.openai_client import call_with_provider_retries
from cli.agent_cli.providers import openai_planner_followup_runtime as followup_runtime
from cli.agent_cli.providers import openai_planner_synthesis as openai_planner_synthesis_helpers
from cli.agent_cli.providers.planner_postprocessing import (
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    sanitize_final_answer_text,
    structured_tool_fallback_text,
)
from cli.agent_cli.providers.responses_503_diagnostics import attach_responses_503_risks


def _fresh_synthesis_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    planner._assert_synthetic_recovery_allowed("fresh synthesis after tool loop")
    route = planner._effective_route_resolution(
        "final_synthesis",
        planner._resolve_route("final_synthesis"),
    )
    route_config = route.config or planner.config
    if planner._route_uses_chat_completions(route_config):
        return planner._chat_route_synthesis(
            route_name="final_synthesis",
            route_config=route_config,
            timeout=route.timeout,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        )
    synthesis_started_at = time.perf_counter()
    kwargs: Dict[str, Any] = {
        "model": route_config.model,
        "instructions": planner.native_tool_system_prompt,
        "input": planner._synthesis_messages(
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        ),
        "store": False,
        "stream": True,
    }
    reasoning = planner._reasoning_request_for_config(route_config)
    if reasoning:
        kwargs["reasoning"] = reasoning
    request_client = planner._route_request_client("final_synthesis", route_config, route.timeout)
    response_text, response = openai_planner_synthesis_helpers.collect_stream_response(
        kwargs=kwargs,
        client=request_client,
        call_with_provider_retries_fn=call_with_provider_retries,
        attach_responses_503_risks_fn=lambda exc, request_kwargs: attach_responses_503_risks(
            exc,
            request_kwargs,
            source="openai_planner.fresh_synthesis",
        ),
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )
    response_items = extract_responses_message_items(response) if response is not None else []
    assistant_text = sanitize_final_answer_text(response_text)
    if not assistant_text and response_items:
        assistant_text = sanitize_final_answer_text(response_items_to_text(response_items))
    if not assistant_text:
        assistant_text = structured_tool_fallback_text(executed_events) or "模型未返回内容。"
    response_items = list(response_items or default_response_items(assistant_text=assistant_text))
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
        turn_events=planner._compose_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=list(executed_item_events or []),
        ),
        timings={
            "synthesis_model_ms": int((time.perf_counter() - synthesis_started_at) * 1000),
            "synthesis_rounds": 1,
        },
    )


def _merge_followup_synthesis_intent(
    planner: Any,
    *,
    synthesized: AgentIntent,
    executed_events: List[ToolEvent],
    started_at: float,
    model_ms: int,
    tool_execution_ms: int,
    rounds: int,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
) -> AgentIntent:
    return followup_runtime.merge_followup_synthesis_intent(
        synthesized=synthesized,
        executed_events=executed_events,
        started_at=started_at,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        rounds=rounds,
        executed_item_events=executed_item_events,
        canonical_turn_events_fn=planner._canonical_turn_events,
    )


def _tool_followup_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    return followup_runtime.build_tool_followup_messages(
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachment_payloads=planner._attachment_payloads(attachments),
        generic_tool_event_summary_lines_fn=generic_tool_event_summary_lines,
        generic_tool_event_context_blocks_fn=generic_tool_event_context_blocks,
        executed_item_event_context_blocks_fn=executed_item_event_context_blocks,
    )


def _fresh_followup_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor: Any,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    planner._assert_synthetic_recovery_allowed("fresh followup after tool loop")
    started_at = time.perf_counter()
    route = planner._effective_route_resolution(
        "tool_followup",
        planner._resolve_route("tool_followup"),
    )
    route_config = route.config or planner.config
    if planner._route_uses_chat_completions(route_config):
        return planner._chat_route_followup(
            route_name="tool_followup",
            route_config=route_config,
            timeout=route.timeout,
            user_text=user_text,
            executed_events=executed_events,
            tool_executor=tool_executor,
            executed_item_events=executed_item_events,
            attachments=attachments,
        )
    request_client = planner._route_request_client("tool_followup", route_config, route.timeout)
    model_ms = 0
    tool_execution_ms = 0
    rounds = 0
    aggregated_item_events = followup_runtime.normalized_item_event_dicts(executed_item_events)
    next_item_index = planner._next_item_index(aggregated_item_events)
    for _ in range(6):
        kwargs: Dict[str, Any] = {
            "model": route_config.model,
            "instructions": planner.native_tool_system_prompt,
            "input": planner._tool_followup_messages(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=aggregated_item_events,
                attachments=attachments,
            ),
            "store": False,
            "stream": True,
            "tools": planner._tool_specs(),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        reasoning = planner._reasoning_request_for_config(route_config)
        if reasoning:
            kwargs["reasoning"] = reasoning

        request_started_at = time.perf_counter()
        response_text, response = openai_planner_synthesis_helpers.collect_stream_response(
            kwargs=kwargs,
            client=request_client,
            call_with_provider_retries_fn=call_with_provider_retries,
            attach_responses_503_risks_fn=lambda exc, request_kwargs: attach_responses_503_risks(
                exc,
                request_kwargs,
                source="openai_planner.fresh_followup",
            ),
            log_responses_request_fn=log_responses_request_fn,
            log_responses_response_fn=log_responses_response_fn,
        )
        model_ms += int((time.perf_counter() - request_started_at) * 1000)
        rounds += 1
        function_calls = planner._response_function_calls(response) if response is not None else []
        response_items = extract_responses_message_items(response) if response is not None else []
        if not function_calls:
            assistant_text = sanitize_final_answer_text(response_text)
            if not assistant_text and response_items:
                assistant_text = sanitize_final_answer_text(response_items_to_text(response_items))
            if assistant_text:
                return followup_runtime.build_followup_direct_answer_intent(
                    assistant_text=assistant_text,
                    response_items=response_items,
                    executed_events=executed_events,
                    executed_item_events=aggregated_item_events,
                    compose_turn_events_fn=planner._compose_turn_events,
                    started_at=started_at,
                    model_ms=model_ms,
                    tool_execution_ms=tool_execution_ms,
                    rounds=rounds,
                )
            synthesized = planner._fresh_synthesis_after_tool_loop(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=aggregated_item_events,
                attachments=attachments,
            )
            return planner._merge_followup_synthesis_intent(
                synthesized=synthesized,
                executed_events=executed_events,
                started_at=started_at,
                model_ms=model_ms,
                tool_execution_ms=tool_execution_ms,
                rounds=rounds,
                executed_item_events=aggregated_item_events,
            )

        for call in function_calls:
            command_text = planner._command_for_function_call(call["name"], call["arguments"])
            if not command_text:
                continue
            execution_started_at = time.perf_counter()
            result = planner._execute_tool_result(tool_executor, command_text)
            tool_execution_ms += int((time.perf_counter() - execution_started_at) * 1000)
            executed_events.extend(list(result.tool_events or []))
            rebased_item_events = followup_runtime.rebase_followup_result_item_events(
                call=call,
                result=result,
                aggregated_item_events=aggregated_item_events,
                next_item_index=next_item_index,
                latest_open_todo_list_item_fn=latest_open_todo_list_item,
                todo_list_turn_event_from_plan_payload_fn=todo_list_turn_event_from_plan_payload,
                rebase_item_events_fn=planner._rebase_item_events,
            )
            aggregated_item_events.extend(rebased_item_events)
            next_item_index = planner._next_item_index(aggregated_item_events)

    synthesized = planner._fresh_synthesis_after_tool_loop(
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=aggregated_item_events,
        attachments=attachments,
    )
    return planner._merge_followup_synthesis_intent(
        synthesized=synthesized,
        executed_events=executed_events,
        started_at=started_at,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        rounds=rounds,
        executed_item_events=aggregated_item_events,
    )
