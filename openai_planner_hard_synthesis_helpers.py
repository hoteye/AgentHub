from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import (
    AgentIntent,
    PromptAttachment,
    ToolEvent,
    default_response_items,
    response_items_to_text,
)
from cli.agent_cli.providers.planner_postprocessing import (
    GENERIC_SYNTHESIS_RULES,
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    sanitize_final_answer_text,
    structured_tool_fallback_text,
)

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]


def fresh_synthesis_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    extract_responses_message_items_fn: Callable[[Any], List[Any]],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    synthesis_started_at = time.perf_counter()
    kwargs: Dict[str, Any] = {
        "model": planner.config.model,
        "instructions": planner.native_tool_system_prompt,
        "input": planner._synthesis_messages(
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        ),
        "store": False,
        "stream": False,
    }
    reasoning = planner._reasoning_request()
    if reasoning:
        kwargs["reasoning"] = reasoning
    log_responses_request_fn("openai_planner.fresh_synthesis", kwargs)
    response = call_with_provider_retries_fn(lambda: planner.client.responses.create(**kwargs))
    log_responses_response_fn("openai_planner.fresh_synthesis", response)
    response_text = planner._response_output_text(response)
    response_items = extract_responses_message_items_fn(response)
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


def merge_followup_synthesis_intent(
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
    synthesized_timings = dict(synthesized.timings or {})
    response_items = list(
        synthesized.response_items
        or default_response_items(assistant_text=synthesized.assistant_text)
    )
    return AgentIntent(
        assistant_text=synthesized.assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
        turn_events=planner._canonical_turn_events(
            assistant_text=synthesized.assistant_text,
            response_items=response_items,
            executed_item_events=list(executed_item_events or []),
            existing_turn_events=list(synthesized.turn_events or []),
        ),
        timings={
            "synthesis_model_ms": model_ms + int(synthesized_timings.get("synthesis_model_ms") or 0),
            "synthesis_rounds": rounds + int(synthesized_timings.get("synthesis_rounds") or 0),
            "tool_execution_ms": tool_execution_ms + int(synthesized_timings.get("tool_execution_ms") or 0),
            "total_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )


def tool_followup_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    parts = [
        "ORIGINAL_USER_REQUEST:",
        user_text,
        "",
        "VERIFIED_TOOL_RESULT_SUMMARY:",
        "\n".join(generic_tool_event_summary_lines(executed_events)) or "- no tool events",
        "",
        "VERIFIED_TOOL_RESULT_CONTEXT_JSON:",
        json.dumps(generic_tool_event_context_blocks(executed_events), ensure_ascii=False, indent=2),
    ]
    item_blocks = executed_item_event_context_blocks(executed_item_events or [])
    if item_blocks:
        parts.extend(
            [
                "",
                "EXECUTED_ITEM_EVENTS_JSON:",
                json.dumps(item_blocks, ensure_ascii=False, indent=2),
            ]
        )
    parts.extend(
        [
            "",
            "Continue solving the original request from these verified tool results and executed item events.",
            "If the current evidence is insufficient, call more tools. If it is sufficient, answer directly.",
        ]
    )
    attachment_payloads = planner._attachment_payloads(attachments)
    if attachment_payloads:
        parts.extend(
            [
                "",
                "ATTACHMENTS_JSON:",
                json.dumps(attachment_payloads, ensure_ascii=False, indent=2),
            ]
        )
    return [{"role": "user", "content": "\n".join(parts)}]


def fresh_followup_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor: PlannerToolExecutor,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    extract_responses_message_items_fn: Callable[[Any], List[Any]],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    started_at = time.perf_counter()
    model_ms = 0
    tool_execution_ms = 0
    rounds = 0
    aggregated_item_events = [
        dict(item)
        for item in list(executed_item_events or [])
        if isinstance(item, dict)
    ]
    next_item_index = planner._next_item_index(aggregated_item_events)
    for _ in range(6):
        kwargs: Dict[str, Any] = {
            "model": planner.config.model,
            "instructions": planner.native_tool_system_prompt,
            "input": planner._tool_followup_messages(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=aggregated_item_events,
                attachments=attachments,
            ),
            "store": False,
            "stream": False,
            "tools": planner._tool_specs(),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        reasoning = planner._reasoning_request()
        if reasoning:
            kwargs["reasoning"] = reasoning

        request_started_at = time.perf_counter()
        log_responses_request_fn("openai_planner.fresh_followup", kwargs)
        response = call_with_provider_retries_fn(lambda: planner.client.responses.create(**kwargs))
        log_responses_response_fn("openai_planner.fresh_followup", response)
        model_ms += int((time.perf_counter() - request_started_at) * 1000)
        rounds += 1
        function_calls = planner._response_function_calls(response)
        response_text = planner._response_output_text(response)
        response_items = extract_responses_message_items_fn(response)
        if not function_calls:
            assistant_text = sanitize_final_answer_text(response_text)
            if not assistant_text and response_items:
                assistant_text = sanitize_final_answer_text(response_items_to_text(response_items))
            if assistant_text:
                return AgentIntent(
                    assistant_text=assistant_text,
                    response_items=list(response_items or default_response_items(assistant_text=assistant_text)),
                    command_text=None,
                    status_hint="tool",
                    tool_events=executed_events,
                    turn_events=planner._compose_turn_events(
                        assistant_text=assistant_text,
                        response_items=list(response_items or default_response_items(assistant_text=assistant_text)),
                        executed_item_events=aggregated_item_events,
                    ),
                    timings={
                        "synthesis_model_ms": model_ms,
                        "synthesis_rounds": rounds,
                        "tool_execution_ms": tool_execution_ms,
                        "total_ms": int((time.perf_counter() - started_at) * 1000),
                    },
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
            rebased_item_events = planner._rebase_item_events(
                [
                    dict(item)
                    for item in list(result.item_events or [])
                    if isinstance(item, dict)
                ],
                start_index=next_item_index,
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


def collect_stream_text(
    planner: Any,
    *,
    kwargs: Dict[str, Any],
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> str:
    log_responses_request_fn("openai_planner.collect_stream_text", kwargs)
    stream = call_with_provider_retries_fn(lambda: planner.client.responses.create(**kwargs))
    text_parts: List[str] = []
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "")
            if delta:
                text_parts.append(str(delta))
        elif event_type == "response.refusal.delta":
            delta = getattr(event, "delta", "")
            if delta:
                text_parts.append(str(delta))
    get_final_response = getattr(stream, "get_final_response", None)
    if callable(get_final_response):
        try:
            log_responses_response_fn("openai_planner.collect_stream_text", get_final_response())
        except Exception:
            pass
    return "".join(text_parts).strip()


def synthesis_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    parts = [
        *GENERIC_SYNTHESIS_RULES,
        "",
        "ORIGINAL_USER_REQUEST:",
        user_text,
        "",
        "TOOL_RESULT_SUMMARY:",
        "\n".join(generic_tool_event_summary_lines(executed_events)) or "- no tool events",
        "",
        "TOOL_RESULT_CONTEXT_JSON:",
        json.dumps(generic_tool_event_context_blocks(executed_events), ensure_ascii=False, indent=2),
    ]
    item_blocks = executed_item_event_context_blocks(executed_item_events or [])
    if item_blocks:
        parts.extend(
            [
                "",
                "EXECUTED_ITEM_EVENTS_JSON:",
                json.dumps(item_blocks, ensure_ascii=False, indent=2),
            ]
        )
    attachment_payloads = planner._attachment_payloads(attachments)
    if attachment_payloads:
        parts.extend(
            [
                "",
                "ATTACHMENTS_JSON:",
                json.dumps(attachment_payloads, ensure_ascii=False, indent=2),
            ]
        )
    return [{"role": "user", "content": "\n".join(parts)}]


def resume_native_tool_followup(
    planner: Any,
    *,
    session: Any,
    user_text: str,
    tool_executor: PlannerToolExecutor,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    previous_response_id: Optional[str] = None,
    continuation_input_items: Optional[List[Dict[str, Any]]] = None,
    terminal_handler: Optional[Callable[..., AgentIntent]] = None,
    turn_engine_cls: Callable[..., Any],
) -> AgentIntent:
    if not continuation_input_items:
        raise ValueError("native tool follow-up requires continuation_input_items")
    rescue_engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=None,
        terminal_handler=terminal_handler,
    )
    return rescue_engine.run(
        user_text=user_text,
        initial_input=[
            dict(item)
            for item in list(continuation_input_items or [])
            if isinstance(item, dict)
        ],
        initial_previous_response_id=previous_response_id,
        initial_executed_events=list(executed_events or []),
        initial_executed_item_events=[
            dict(item)
            for item in list(executed_item_events or [])
            if isinstance(item, dict)
        ],
    )
