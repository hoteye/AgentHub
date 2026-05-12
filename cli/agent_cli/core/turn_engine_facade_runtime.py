from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.core import turn_engine_interrupt_runtime as turn_engine_interrupt_runtime_service
from cli.agent_cli.core import turn_engine_runtime as turn_engine_runtime_service
from cli.agent_cli.core import turn_engine_tool_runtime as turn_engine_tool_runtime_service
from cli.agent_cli.models import AgentIntent, ResponseInputItem, ToolEvent


def planner_trace_delegation_summary(tool_calls: List[Any]) -> Dict[str, Any]:
    try:
        from cli.agent_cli.providers.delegation_policy import planner_trace_delegation_summary as summary_fn
    except ImportError:
        return {
            "delegation_decision": "none",
            "delegation_policy_decision": "stay_local",
            "delegation_policy_source": "delegation_policy",
            "delegation_policy_reason": "no_delegation_tools_observed",
        }
    return summary_fn(tool_calls)


def structured_tool_fallback_text(events: List[ToolEvent]) -> str:
    return turn_engine_runtime_service.structured_tool_fallback_text(events)


def tool_call_preamble_text(tool_name: str, arguments: Dict[str, Any]) -> str:
    return turn_engine_tool_runtime_service.tool_call_preamble_text(tool_name, arguments)


def synthetic_agent_message_event(*, item_id: str, text: str) -> Dict[str, Any]:
    return turn_engine_tool_runtime_service.synthetic_agent_message_event(item_id=item_id, text=text)


def annotate_tool_events_with_provider_call(
    *,
    tool_events: List[ToolEvent],
    provider_call_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    execution_tool: str = "",
    provider_item_type: str = "",
    provider_raw_item: Dict[str, Any] | None = None,
) -> List[ToolEvent]:
    return turn_engine_tool_runtime_service.annotate_tool_events_with_provider_call(
        tool_events=tool_events,
        provider_call_id=provider_call_id,
        tool_name=tool_name,
        arguments=arguments,
        execution_tool=execution_tool,
        provider_item_type=provider_item_type,
        provider_raw_item=provider_raw_item,
    )


def compose_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return turn_engine_tool_runtime_service.compose_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=executed_item_events,
    )


class TurnEngineFacadeMixin:
    def _emit_turn_event(self, event: Dict[str, Any]) -> None:
        turn_engine_interrupt_runtime_service.emit_turn_event(
            event,
            callback=self.turn_event_callback,
        )

    def _emit_turn_events(self, events: List[Dict[str, Any]]) -> None:
        turn_engine_interrupt_runtime_service.emit_turn_events(
            events,
            emit_turn_event_fn=self._emit_turn_event,
        )

    def _command_for_call(self, name: str, arguments: Dict[str, Any]) -> Optional[str]:
        if self.command_builder is not None:
            return self.command_builder(name, arguments)
        return json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False)

    @staticmethod
    def _invoke_handler(
        handler: Callable[..., AgentIntent],
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: List[Dict[str, Any]],
        previous_response_id: Optional[str] = None,
        continuation_input_items: Optional[List[Dict[str, Any]]] = None,
        initial_send_error: Optional[Exception] = None,
    ) -> AgentIntent:
        return turn_engine_runtime_service.invoke_handler(
            handler,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            previous_response_id=previous_response_id,
            continuation_input_items=continuation_input_items,
            initial_send_error=initial_send_error,
        )

    @staticmethod
    def _final_intent(
        *,
        assistant_text: str,
        response_items: Optional[List[ResponseInputItem]],
        executed_events: List[ToolEvent],
        executed_item_events: List[Dict[str, Any]],
        model_ms: int,
        tool_execution_ms: int,
        planning_rounds: int,
        planning_trace: List[Dict[str, Any]],
        synthesis_model_ms: int,
        synthesis_rounds: int,
        total_ms: int,
    ) -> AgentIntent:
        return turn_engine_tool_runtime_service.final_intent(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            model_ms=model_ms,
            tool_execution_ms=tool_execution_ms,
            planning_rounds=planning_rounds,
            planning_trace=planning_trace,
            synthesis_model_ms=synthesis_model_ms,
            synthesis_rounds=synthesis_rounds,
            total_ms=total_ms,
        )

    @staticmethod
    def _fallback_intent(
        fallback: AgentIntent,
        *,
        executed_events: List[ToolEvent],
        executed_item_events: List[Dict[str, Any]],
        model_ms: int,
        tool_execution_ms: int,
        planning_rounds: int,
        total_ms: int,
    ) -> AgentIntent:
        return turn_engine_tool_runtime_service.fallback_intent(
            fallback,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            model_ms=model_ms,
            tool_execution_ms=tool_execution_ms,
            planning_rounds=planning_rounds,
            total_ms=total_ms,
        )
