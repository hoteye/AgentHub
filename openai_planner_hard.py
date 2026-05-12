from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import openai_planner_hard_event_helpers as event_helpers
import openai_planner_hard_logging_helpers as logging_helpers
import openai_planner_hard_plan_helpers as plan_helpers
import openai_planner_hard_prompt_helpers as prompt_helpers
import openai_planner_hard_pure_helpers as pure_helpers
import openai_planner_hard_response_helpers as response_helpers
import openai_planner_hard_synthesis_helpers as synthesis_helpers
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    PromptAttachment,
    ToolEvent,
)
from cli.agent_cli.providers.adapters.openai_responses import (
    OpenAIResponsesSession,
    extract_responses_message_items,
    extract_responses_output_text,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_client import build_openai_client, call_with_provider_retries
from cli.agent_cli.providers.planners_common import BasePlanner
from cli.agent_cli.providers.tool_calls import (
    command_for_tool_call as _command_for_tool_call_impl,
    plugin_system_prompt_addendum as _plugin_system_prompt_addendum_impl,
    tool_result_payload as _tool_result_payload_impl,
)
from cli.agent_cli.providers.tool_specs import (
    command_text_patterns as _command_text_patterns_impl,
    provider_tool_names as _provider_tool_names_impl,
    responses_minimal_provider_tool_names as _responses_minimal_provider_tool_names_impl,
    responses_minimal_provider_tool_specs as _responses_minimal_provider_tool_specs_impl,
    responses_provider_tool_specs as _responses_provider_tool_specs_impl,
)

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]


def _log_responses_request(stage: str, kwargs: Dict[str, Any]) -> None:
    logging_helpers.log_responses_request(
        stage,
        kwargs,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        json_ready_fn=json_ready,
    )


def _log_responses_response(stage: str, response: Any) -> None:
    logging_helpers.log_responses_response(
        stage,
        response,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        json_ready_fn=json_ready,
    )


def _plugin_system_prompt_addendum(
    *,
    plugin_manager_factory: Optional[Callable[[], Any]] = None,
) -> str:
    return _plugin_system_prompt_addendum_impl(plugin_manager_factory=plugin_manager_factory)


class OpenAIPlanner(BasePlanner):
    _COMMAND_PATTERN = re.compile(r"(?m)(/(?:shell|apply_patch|grep_files|read_file|list_dir|file_list|file_search|file_read|office_skills|office_run|web_search|web_fetch|open|click|find)\b[^\r\n`]*)")
    _FOLLOWUP_COMMAND_PATTERN = re.compile(
        r"\s+/(?:shell|apply_patch|grep_files|read_file|list_dir|file_list|file_search|file_read|office_skills|office_run|web_search|web_fetch|open|click|find)\b"
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        host_platform: HostPlatform | None = None,
        cwd: str | None = None,
        plugin_manager_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            config,
            host_platform=host_platform,
            cwd=cwd,
            plugin_manager_factory=plugin_manager_factory,
        )
        self.client = build_openai_client(config)
        init_state = prompt_helpers.planner_init_state(
            config=self.config,
            host_platform=self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
            command_text_patterns_fn=_command_text_patterns_impl,
            provider_tool_names_fn=_provider_tool_names_impl,
            minimal_provider_tool_names_fn=_responses_minimal_provider_tool_names_impl,
            plugin_prompt_addendum_fn=_plugin_system_prompt_addendum,
        )
        self._COMMAND_PATTERN = init_state["command_pattern"]
        self._FOLLOWUP_COMMAND_PATTERN = init_state["followup_command_pattern"]
        self.system_prompt = init_state["system_prompt"]
        self.native_tool_system_prompt = init_state["native_tool_system_prompt"]

    @staticmethod
    def _message_input_item(role: str, content: str) -> Dict[str, Any]:
        return pure_helpers.message_input_item(role, content)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
        return pure_helpers.extract_json_payload(raw_text)

    @staticmethod
    def _quote_arg(value: Any) -> str:
        return pure_helpers.quote_arg(value)

    @staticmethod
    def _optional_bool(value: Any, default: bool = False) -> bool:
        return pure_helpers.optional_bool(value, default)

    def _tool_specs(self) -> List[Dict[str, Any]]:
        return _responses_minimal_provider_tool_specs_impl(
            self.config,
            self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def _reasoning_request(self) -> Optional[Dict[str, Any]]:
        effort = str(self.config.reasoning_effort or "").strip()
        if not effort:
            return None
        return {
            "effort": effort,
            "summary": "auto",
        }

    def _command_for_function_call(self, name: str, arguments: Dict[str, Any]) -> Optional[str]:
        return _command_for_tool_call_impl(
            name,
            arguments,
            self.host_platform,
            optional_bool_fn=self._optional_bool,
            quote_arg_fn=self._quote_arg,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    @staticmethod
    def _response_function_calls(response: Any) -> List[Dict[str, Any]]:
        return response_helpers.response_function_calls(response)

    @staticmethod
    def _response_output_text(response: Any) -> str:
        return response_helpers.response_output_text(
            response,
            extract_responses_output_text_fn=extract_responses_output_text,
        )

    @staticmethod
    def _tool_output_item(
        call_id: str,
        command_text: Optional[str],
        assistant_text: str,
        events: List[ToolEvent],
    ) -> Dict[str, Any]:
        return response_helpers.tool_output_item(
            call_id,
            command_text,
            assistant_text,
            events,
            tool_result_payload_fn=_tool_result_payload_impl,
        )

    @staticmethod
    def _next_item_index(events: List[Dict[str, Any]]) -> int:
        return event_helpers.next_item_index(events)

    @classmethod
    def _rebase_item_events(cls, events: List[Dict[str, Any]], *, start_index: int) -> List[Dict[str, Any]]:
        return event_helpers.rebase_item_events(events, start_index=start_index)

    @classmethod
    def _compose_turn_events(
        cls,
        *,
        assistant_text: str,
        response_items: List[Any],
        executed_item_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return event_helpers.compose_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=executed_item_events,
        )

    @staticmethod
    def _rewrite_existing_turn_events(
        existing_turn_events: List[Dict[str, Any]],
        *,
        final_text: str,
    ) -> List[Dict[str, Any]]:
        return event_helpers.rewrite_existing_turn_events(
            existing_turn_events,
            final_text=final_text,
        )

    def _canonical_turn_events(
        self,
        *,
        assistant_text: str,
        response_items: List[Any],
        executed_item_events: List[Dict[str, Any]],
        existing_turn_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        return event_helpers.canonical_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=executed_item_events,
            existing_turn_events=existing_turn_events,
            rewrite_existing_turn_events_fn=self._rewrite_existing_turn_events,
            compose_turn_events_fn=self._compose_turn_events,
        )

    @staticmethod
    def _tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return event_helpers.tool_item_events_from_turn_events(turn_events)

    @staticmethod
    def _execute_tool_result(tool_executor: PlannerToolExecutor, command_text: str) -> CommandExecutionResult:
        return event_helpers.execute_tool_result(tool_executor, command_text)

    def _history_for_conversation(
        self,
        history: List[Dict[str, str]],
        *,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        return event_helpers.history_for_conversation(
            history,
            input_items=input_items,
            input_items_have_assistant_turn_fn=self._input_items_have_assistant_turn,
        )

    def _fresh_synthesis_after_tool_loop(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> AgentIntent:
        return synthesis_helpers.fresh_synthesis_after_tool_loop(
            self,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
            call_with_provider_retries_fn=call_with_provider_retries,
            extract_responses_message_items_fn=extract_responses_message_items,
            log_responses_request_fn=_log_responses_request,
            log_responses_response_fn=_log_responses_response,
        )

    def _merge_followup_synthesis_intent(
        self,
        *,
        synthesized: AgentIntent,
        executed_events: List[ToolEvent],
        started_at: float,
        model_ms: int,
        tool_execution_ms: int,
        rounds: int,
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        return synthesis_helpers.merge_followup_synthesis_intent(
            self,
            synthesized=synthesized,
            executed_events=executed_events,
            started_at=started_at,
            model_ms=model_ms,
            tool_execution_ms=tool_execution_ms,
            rounds=rounds,
            executed_item_events=executed_item_events,
        )

    def _tool_followup_messages(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> List[Dict[str, Any]]:
        return synthesis_helpers.tool_followup_messages(
            self,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        )

    def _fresh_followup_after_tool_loop(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        tool_executor: PlannerToolExecutor,
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> AgentIntent:
        return synthesis_helpers.fresh_followup_after_tool_loop(
            self,
            user_text=user_text,
            executed_events=executed_events,
            tool_executor=tool_executor,
            executed_item_events=executed_item_events,
            attachments=attachments,
            call_with_provider_retries_fn=call_with_provider_retries,
            extract_responses_message_items_fn=extract_responses_message_items,
            log_responses_request_fn=_log_responses_request,
            log_responses_response_fn=_log_responses_response,
        )

    def _collect_stream_text(self, **kwargs: Any) -> str:
        return synthesis_helpers.collect_stream_text(
            self,
            kwargs=kwargs,
            call_with_provider_retries_fn=call_with_provider_retries,
            log_responses_request_fn=_log_responses_request,
            log_responses_response_fn=_log_responses_response,
        )

    def _synthesis_messages(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> List[Dict[str, Any]]:
        return synthesis_helpers.synthesis_messages(
            self,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        )

    def _resume_native_tool_followup(
        self,
        *,
        session: OpenAIResponsesSession,
        user_text: str,
        tool_executor: PlannerToolExecutor,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        previous_response_id: Optional[str] = None,
        continuation_input_items: Optional[List[Dict[str, Any]]] = None,
        terminal_handler: Optional[Callable[..., AgentIntent]] = None,
    ) -> AgentIntent:
        return synthesis_helpers.resume_native_tool_followup(
            self,
            session=session,
            user_text=user_text,
            tool_executor=tool_executor,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            previous_response_id=previous_response_id,
            continuation_input_items=continuation_input_items,
            terminal_handler=terminal_handler,
            turn_engine_cls=TurnEngine,
        )

    def _normalize_command_text(self, command_text: Optional[str]) -> Optional[str]:
        return pure_helpers.normalize_command_text(
            command_text,
            followup_command_pattern=self._FOLLOWUP_COMMAND_PATTERN,
            host_platform=self.host_platform,
        )

    def _extract_command_text(self, raw_text: str) -> Optional[str]:
        return pure_helpers.extract_command_text(
            raw_text,
            command_pattern=self._COMMAND_PATTERN,
            normalize_command_text_fn=self._normalize_command_text,
        )

    def _intent_from_raw_text(
        self,
        raw_text: str,
        *,
        allow_command_pattern_fallback: bool = True,
    ) -> AgentIntent:
        return pure_helpers.intent_from_raw_text(
            raw_text,
            extract_json_payload_fn=self._extract_json_payload,
            normalize_command_text_fn=self._normalize_command_text,
            extract_command_text_fn=self._extract_command_text,
            command_pattern=self._COMMAND_PATTERN,
            allow_command_pattern_fallback=allow_command_pattern_fallback,
        )

    def plan(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        tool_executor: Optional[PlannerToolExecutor] = None,
        attachments: Optional[List[PromptAttachment]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentIntent:
        return plan_helpers.plan(
            self,
            user_text,
            history,
            tool_executor=tool_executor,
            attachments=attachments,
            input_items=input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            responses_session_cls=OpenAIResponsesSession,
            turn_engine_cls=TurnEngine,
        )

    def _plan_without_native_tools(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        attachments: Optional[List[PromptAttachment]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        return plan_helpers.plan_without_native_tools(
            self,
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )
