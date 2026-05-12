from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers import openai_planner_synthesis as openai_planner_synthesis_helpers


def chat_route_followup(
    planner: Any,
    *,
    route_name: str,
    route_config: ProviderConfig,
    timeout: int | None,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor: Callable[[str], Any],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    turn_engine_cls: type[TurnEngine],
    build_tool_followup_initial_input_fn: Callable[..., List[Dict[str, Any]]],
) -> AgentIntent:
    session = planner._chat_route_session(
        route_name=route_name,
        route_config=route_config,
        timeout=timeout,
    )
    initial_input = build_tool_followup_initial_input_fn(
        system_prompt=planner._chat_route_system_prompt(route_config),
        followup_messages=planner._tool_followup_messages(
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        ),
    )

    def _terminal_handler(
        followup_user_text: str,
        followup_events: List[ToolEvent],
        followup_item_events: Optional[List[Dict[str, Any]]] = None,
        _previous_response_id: Optional[str] = None,
        _continuation_input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        return planner._fresh_synthesis_after_tool_loop(
            user_text=followup_user_text,
            executed_events=followup_events,
            executed_item_events=followup_item_events,
            attachments=attachments,
        )

    engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=planner._command_for_function_call,
        terminal_handler=_terminal_handler,
        max_rounds=6,
    )
    return engine.run(
        user_text=user_text,
        initial_input=initial_input,
        initial_executed_events=executed_events,
        initial_executed_item_events=executed_item_events,
    )


def collect_stream_text(
    *,
    planner: Any,
    kwargs: Dict[str, Any],
    call_with_provider_retries_fn: Callable[..., Any],
    attach_responses_503_risks_fn: Callable[[Exception, Dict[str, Any]], Exception],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> str:
    return openai_planner_synthesis_helpers.collect_stream_text(
        kwargs=kwargs,
        client=planner.client,
        call_with_provider_retries_fn=call_with_provider_retries_fn,
        attach_responses_503_risks_fn=attach_responses_503_risks_fn,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )
