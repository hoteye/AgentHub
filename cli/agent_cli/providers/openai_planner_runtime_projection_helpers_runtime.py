from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, ToolEvent, default_response_items
from cli.agent_cli.models_response_items import terminal_failure_message
from cli.agent_cli.providers import (
    openai_planner_runtime_normalization_helpers_runtime as normalization_helpers,
)
from cli.agent_cli.providers import openai_planner_runtime_pure_helpers_runtime as pure_helpers
from cli.agent_cli.providers.planner_postprocessing import structured_tool_fallback_text


def _terminal_failure_protocol_diagnostics(
    *,
    reason: str,
    error_message: str,
    protocol_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(protocol_diagnostics or {})
    merged["turn_terminal_state"] = {
        "result": "failed",
        "reason": str(reason or "").strip() or "final_answer_missing",
        "error_message": str(error_message or "").strip() or "turn failed",
    }
    return merged


def _failed_turn_events(
    turn_events: List[Dict[str, Any]],
    *,
    error_message: str,
) -> List[Dict[str, Any]]:
    normalized_events = [dict(item) for item in list(turn_events or []) if isinstance(item, dict)]
    if not normalized_events:
        return [{"type": "turn.started"}, {"type": "turn.failed", "error": {"message": error_message}}]
    updated: List[Dict[str, Any]] = []
    terminal_replaced = False
    for event in normalized_events:
        event_type = str(event.get("type") or "").strip()
        if event_type in {"turn.completed", "turn.failed"}:
            if not terminal_replaced:
                updated.append({"type": "turn.failed", "error": {"message": error_message}})
                terminal_replaced = True
            continue
        updated.append(dict(event))
    if not terminal_replaced:
        updated.append({"type": "turn.failed", "error": {"message": error_message}})
    return updated


def _fallback_assistant_text(
    *,
    executed_events: List[ToolEvent],
    failure_message: str | None = None,
) -> str:
    base_text = structured_tool_fallback_text(executed_events) or "模型未返回内容。"
    detail = str(failure_message or "").strip()
    if not detail:
        return base_text
    return f"{base_text}\n回答阶段错误：{detail}"


def fallback_tool_intent(
    *,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    compose_turn_events_fn: Callable[..., List[Dict[str, Any]]],
    failure_reason: str = "final_answer_missing",
    failure_message: str | None = None,
) -> AgentIntent:
    assistant_text = _fallback_assistant_text(
        executed_events=executed_events,
        failure_message=failure_message,
    )
    response_items = default_response_items(assistant_text=assistant_text)
    terminal_error = str(failure_message or "").strip() or (
        "工具已执行完成，但最终回答阶段未产出可展示内容。"
    )
    protocol_diagnostics = _terminal_failure_protocol_diagnostics(
        reason=failure_reason,
        error_message=terminal_error,
    )
    turn_events = compose_turn_events_fn(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=list(executed_item_events or []),
    )
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="degraded",
        protocol_diagnostics=protocol_diagnostics,
        tool_events=list(executed_events),
        turn_events=_failed_turn_events(
            turn_events,
            error_message=terminal_failure_message(protocol_diagnostics=protocol_diagnostics),
        ),
    )


def project_native_tool_loop_intent(
    *,
    raw_intent: AgentIntent,
    user_text: str,
    attachments: Optional[List[Any]] = None,
    total_elapsed_ms: int,
    tool_item_events_from_turn_events_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    synthetic_recovery_allowed: bool,
    synthesize_after_tool_loop_fn: Callable[..., AgentIntent],
    canonical_turn_events_fn: Callable[..., List[Dict[str, Any]]],
) -> AgentIntent:
    normalized = normalization_helpers.normalized_native_tool_loop_intent(
        raw_intent,
        tool_item_events_from_turn_events_fn=tool_item_events_from_turn_events_fn,
    )
    raw_tool_events = raw_intent.tool_events
    executed_tool_events = list(raw_tool_events or [])
    assistant_text = normalized.assistant_text
    final_response_items = list(normalized.response_items)
    raw_timings = dict(normalized.raw_timings)
    synthesized_timings: Dict[str, Any] = {}
    turn_events = list(normalized.turn_events)
    tool_item_events = list(normalized.tool_item_events)
    protocol_diagnostics = dict(raw_intent.protocol_diagnostics or {})
    terminal_failure_reason = ""
    synthesis_failure_message = ""

    needs_synthesis = pure_helpers.native_tool_loop_needs_synthesis(
        assistant_text=assistant_text,
        tool_events=executed_tool_events,
        tool_item_events=tool_item_events,
        response_has_text=normalized.response_has_text,
    )
    if needs_synthesis:
        if not synthetic_recovery_allowed:
            assistant_text = structured_tool_fallback_text(executed_tool_events) if raw_tool_events else assistant_text
            if raw_tool_events:
                terminal_failure_reason = "final_answer_missing"
        else:
            try:
                synthesized = synthesize_after_tool_loop_fn(
                    user_text=user_text,
                    executed_events=list(executed_tool_events),
                    executed_item_events=tool_item_events,
                    attachments=attachments,
                )
                synthesized_timings = dict(synthesized.timings or {})
                normalized_synthesized = normalization_helpers.normalized_response_payload(
                    assistant_text=synthesized.assistant_text,
                    response_items=list(synthesized.response_items or []),
                )
                if normalized_synthesized.assistant_text:
                    assistant_text = normalized_synthesized.assistant_text
                    final_response_items = list(
                        synthesized.response_items
                        or default_response_items(assistant_text=assistant_text)
                    )
                    if synthesized.turn_events:
                        turn_events = normalization_helpers.normalized_turn_event_dicts(
                            list(synthesized.turn_events or [])
                        )
                else:
                    terminal_failure_reason = "final_answer_missing"
            except Exception as exc:
                terminal_failure_reason = "final_synthesis_error"
                synthesis_failure_message = f"{type(exc).__name__}: {exc}"
    elif not assistant_text and tool_item_events:
        assistant_text = (
            structured_tool_fallback_text(executed_tool_events)
            if raw_tool_events
            else assistant_text
        )
        if raw_tool_events:
            terminal_failure_reason = "final_answer_missing"

    if not assistant_text:
        assistant_text = (
            structured_tool_fallback_text(executed_tool_events)
            if raw_tool_events
            else "模型未返回内容。"
        )
    if not final_response_items:
        final_response_items = list(default_response_items(assistant_text=assistant_text))

    if raw_tool_events and terminal_failure_reason:
        assistant_text = _fallback_assistant_text(
            executed_events=executed_tool_events,
            failure_message=synthesis_failure_message,
        )
        final_response_items = list(default_response_items(assistant_text=assistant_text))
        protocol_diagnostics = _terminal_failure_protocol_diagnostics(
            reason=terminal_failure_reason,
            error_message=(
                synthesis_failure_message
                or "工具已执行完成，但最终回答阶段未产出可展示内容。"
            ),
            protocol_diagnostics=protocol_diagnostics,
        )
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=list(final_response_items),
            command_text=None,
            status_hint="degraded",
            protocol_diagnostics=protocol_diagnostics,
            tool_events=raw_tool_events,
            turn_events=_failed_turn_events(
                canonical_turn_events_fn(
                    assistant_text=assistant_text,
                    response_items=list(final_response_items),
                    executed_item_events=tool_item_events,
                    existing_turn_events=turn_events,
                ),
                error_message=terminal_failure_message(protocol_diagnostics=protocol_diagnostics),
            ),
            timings=pure_helpers.merge_native_tool_timings(
                raw_timings=raw_timings,
                synthesis_timings=synthesized_timings,
                total_elapsed_ms=total_elapsed_ms,
                tool_call_count=len(executed_tool_events),
            ),
        )

    return AgentIntent(
        assistant_text=assistant_text,
        response_items=list(final_response_items),
        command_text=None,
        status_hint="tool" if raw_tool_events else "llm",
        protocol_diagnostics=protocol_diagnostics,
        tool_events=raw_tool_events,
        turn_events=canonical_turn_events_fn(
            assistant_text=assistant_text,
            response_items=list(final_response_items),
            executed_item_events=tool_item_events,
            existing_turn_events=turn_events,
        ),
        timings=pure_helpers.merge_native_tool_timings(
            raw_timings=raw_timings,
            synthesis_timings=synthesized_timings,
            total_elapsed_ms=total_elapsed_ms,
            tool_call_count=len(executed_tool_events),
        ),
    )


def project_native_without_tools_intent(
    *,
    result: Any,
    initial_model_ms: int,
    total_elapsed_ms: int,
    compose_turn_events_fn: Callable[..., List[Dict[str, Any]]],
) -> AgentIntent:
    normalized = normalization_helpers.normalized_response_payload(
        assistant_text=getattr(result, "output_text", ""),
        response_items=list(getattr(result, "response_items", []) or []),
    )
    assistant_text = normalized.assistant_text or "模型未返回内容。"
    final_response_items = list(
        normalized.response_items or default_response_items(assistant_text=assistant_text)
    )
    timings = pure_helpers.planning_only_timings(
        initial_model_ms=initial_model_ms,
        total_elapsed_ms=total_elapsed_ms,
    )
    usage = getattr(result, "trace", {}).get("usage") if isinstance(getattr(result, "trace", None), dict) else None
    if isinstance(usage, dict):
        timings["token_usage"] = dict(usage)
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=final_response_items,
        command_text=None,
        status_hint="llm",
        turn_events=compose_turn_events_fn(
            assistant_text=assistant_text,
            response_items=final_response_items,
            executed_item_events=[],
        ),
        timings=timings,
    )


def project_legacy_json_intent(
    *,
    intent: AgentIntent,
    initial_model_ms: int,
    total_elapsed_ms: int,
) -> AgentIntent:
    intent.timings = pure_helpers.planning_only_timings(
        initial_model_ms=initial_model_ms,
        total_elapsed_ms=total_elapsed_ms,
    )
    return intent


__all__ = [
    "fallback_tool_intent",
    "project_legacy_json_intent",
    "project_native_tool_loop_intent",
    "project_native_without_tools_intent",
]
