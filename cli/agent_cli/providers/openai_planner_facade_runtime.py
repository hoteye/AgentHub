from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, CommandExecutionResult
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers import openai_planner_class_runtime as openai_planner_class_runtime_helpers
from cli.agent_cli.providers import openai_planner_intent_facade_runtime as openai_planner_intent_facade_runtime_helpers
from cli.agent_cli.providers import openai_planner_runtime as openai_planner_runtime_helpers
from cli.agent_cli.providers import openai_planner_support_runtime as openai_planner_support_runtime_helpers
from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service
from cli.agent_cli.providers.tool_calls import command_for_tool_call as _command_for_tool_call_impl
from cli.agent_cli.providers.tool_specs import (
    responses_minimal_provider_tool_specs as _responses_minimal_provider_tool_specs_impl,
)


class OpenAIPlannerFacadeMixin:
    @staticmethod
    def _message_input_item(role: str, content: str) -> Dict[str, Any]:
        # Keep the non-native JSON planning path on the last known-good flat wire shape.
        # The native Responses tool loop uses typed message items separately.
        return openai_planner_support_runtime_helpers.message_input_item(role, content)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
        return openai_planner_support_runtime_helpers.extract_json_payload(raw_text)

    @staticmethod
    def _quote_arg(value: Any) -> str:
        return openai_planner_support_runtime_helpers.quote_arg(value)

    @staticmethod
    def _optional_bool(value: Any, default: bool = False) -> bool:
        return openai_planner_support_runtime_helpers.optional_bool(value, default)

    def _tool_specs(self) -> List[Dict[str, Any]]:
        return _responses_minimal_provider_tool_specs_impl(
            self.config,
            self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def _command_for_function_call(self, name: str, arguments: Dict[str, Any]) -> Optional[str]:
        return openai_planner_class_runtime_helpers.command_for_function_call(
            name=name,
            arguments=arguments,
            host_platform=self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
            optional_bool_fn=self._optional_bool,
            quote_arg_fn=self._quote_arg,
            command_for_tool_call_fn=_command_for_tool_call_impl,
        )

    @staticmethod
    def _response_function_calls(response: Any) -> List[Dict[str, Any]]:
        return openai_planner_tool_runtime_service._response_function_calls(response)

    @staticmethod
    def _response_output_text(response: Any) -> str:
        return openai_planner_tool_runtime_service._response_output_text(response)

    @staticmethod
    def _tool_output_item(call_id: str, command_text: Optional[str], assistant_text: str, events: List[Any]) -> Dict[str, Any]:
        return openai_planner_tool_runtime_service._tool_output_item(call_id, command_text, assistant_text, events)

    @staticmethod
    def _next_item_index(events: List[Dict[str, Any]]) -> int:
        return openai_planner_tool_runtime_service._next_item_index(events)

    @classmethod
    def _rebase_item_events(cls, events: List[Dict[str, Any]], *, start_index: int) -> List[Dict[str, Any]]:
        return openai_planner_tool_runtime_service._rebase_item_events(events, start_index=start_index)

    @classmethod
    def _compose_turn_events(
        cls,
        *,
        assistant_text: str,
        response_items: List[Any],
        executed_item_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return openai_planner_tool_runtime_service._compose_turn_events(
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
        return openai_planner_tool_runtime_service._rewrite_existing_turn_events(
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
        return openai_planner_tool_runtime_service._canonical_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=executed_item_events,
            existing_turn_events=existing_turn_events,
        )

    @staticmethod
    def _tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return openai_planner_tool_runtime_service._tool_item_events_from_turn_events(turn_events)

    @staticmethod
    def _execute_tool_result(tool_executor: Any, command_text: str) -> CommandExecutionResult:
        return openai_planner_tool_runtime_service._execute_tool_result(tool_executor, command_text)

    def _history_for_conversation(
        self,
        history: List[Dict[str, str]],
        *,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        return openai_planner_intent_facade_runtime_helpers.history_for_conversation(
            self,
            history,
            input_items=input_items,
        )

    def _synthetic_recovery_allowed(self) -> bool:
        return openai_planner_intent_facade_runtime_helpers.synthetic_recovery_allowed(self)

    def _assert_synthetic_recovery_allowed(self, path_name: str) -> None:
        openai_planner_intent_facade_runtime_helpers.assert_synthetic_recovery_allowed(self, path_name)

    def _normalize_command_text(self, command_text: Optional[str]) -> Optional[str]:
        return openai_planner_intent_facade_runtime_helpers.normalize_command_text(self, command_text)

    def _extract_command_text(self, raw_text: str) -> Optional[str]:
        return openai_planner_intent_facade_runtime_helpers.extract_command_text(self, raw_text)

    def _intent_from_raw_text(
        self,
        raw_text: str,
        *,
        allow_command_pattern_fallback: bool = True,
    ) -> AgentIntent:
        return openai_planner_intent_facade_runtime_helpers.intent_from_raw_text(
            self,
            raw_text,
            allow_command_pattern_fallback=allow_command_pattern_fallback,
        )

    def _plan_native_without_tools(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        attachments: Optional[List[Any]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Optional[Any] = None,
        provider_session_id: Optional[str] = None,
        provider_turn_id: Optional[str] = None,
        provider_sandbox_mode: Optional[str] = None,
    ) -> AgentIntent:
        return openai_planner_runtime_helpers.plan_native_without_tools(
            self,
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            provider_session_id=provider_session_id,
            provider_turn_id=provider_turn_id,
            provider_sandbox_mode=provider_sandbox_mode,
            responses_session_cls=OpenAIResponsesSession,
        )

    def _plan_without_native_tools(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        attachments: Optional[List[Any]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        return openai_planner_runtime_helpers.plan_without_native_tools(
            self,
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )
