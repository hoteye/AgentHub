from __future__ import annotations

import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import (
    AgentIntent,
    PromptAttachment,
    ToolEvent,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.openai_client import build_openai_client, call_with_provider_retries
from cli.agent_cli.providers.responses_503_diagnostics import attach_responses_503_risks
from cli.agent_cli.providers import openai_planner_class_runtime as openai_planner_class_runtime_helpers
from cli.agent_cli.providers import openai_planner_coordination_runtime as openai_planner_coordination_runtime_helpers
from cli.agent_cli.providers.openai_planner_facade_runtime import OpenAIPlannerFacadeMixin
from cli.agent_cli.providers import openai_planner_logging_runtime as openai_planner_logging_runtime_helpers
from cli.agent_cli.providers import openai_planner_loop_runtime as openai_planner_loop_runtime_helpers
from cli.agent_cli.providers import openai_planner_runtime as openai_planner_runtime_helpers
from cli.agent_cli.providers import openai_planner_support_runtime as openai_planner_support_runtime_helpers
from cli.agent_cli.providers import openai_planner_synthesis as openai_planner_synthesis_helpers
from cli.agent_cli.providers.openai_planner_routing import OpenAIPlannerRoutingMixin
from cli.agent_cli.providers.planners_common import BasePlanner
from cli.agent_cli.providers.system_prompts import build_openai_json_system_prompt, build_openai_native_system_prompt
from cli.agent_cli.providers.tool_specs import (
    command_text_patterns as _command_text_patterns_impl,
    provider_tool_names as _provider_tool_names_impl,
    responses_minimal_provider_tool_names as _responses_minimal_provider_tool_names_impl,
)

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]
def _log_responses_request(stage: str, kwargs: Dict[str, Any]) -> None:
    openai_planner_logging_runtime_helpers.log_responses_request(
        stage,
        kwargs,
        support_runtime=openai_planner_support_runtime_helpers,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        json_ready_fn=json_ready,
    )


def _log_responses_response(stage: str, response: Any) -> None:
    openai_planner_logging_runtime_helpers.log_responses_response(
        stage,
        response,
        support_runtime=openai_planner_support_runtime_helpers,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        json_ready_fn=json_ready,
    )


class OpenAIPlanner(OpenAIPlannerFacadeMixin, OpenAIPlannerRoutingMixin, BasePlanner):
    _COMMAND_PATTERN = re.compile(r"(?m)(/(?:shell|apply_patch|glob_files|grep_files|read_file|list_dir|file_list|file_search|file_read|office_skills|office_run|web_search|web_fetch|browser|open|click|find)\b[^\r\n`]*)")
    _FOLLOWUP_COMMAND_PATTERN = re.compile(
        r"\s+/(?:shell|apply_patch|glob_files|grep_files|read_file|list_dir|file_list|file_search|file_read|office_skills|office_run|web_search|web_fetch|browser|open|click|find)\b"
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
        init_state = openai_planner_class_runtime_helpers.planner_init_state(
            config=self.config,
            host_platform=self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
            command_text_patterns_fn=_command_text_patterns_impl,
            provider_tool_names_fn=_provider_tool_names_impl,
            minimal_provider_tool_names_fn=_responses_minimal_provider_tool_names_impl,
            build_json_system_prompt_fn=build_openai_json_system_prompt,
            build_native_system_prompt_fn=build_openai_native_system_prompt,
        )
        self._COMMAND_PATTERN = init_state["command_pattern"]
        self._FOLLOWUP_COMMAND_PATTERN = init_state["followup_command_pattern"]
        self.resolved_interaction_contract = init_state["resolved_interaction_contract"]
        self.reference_parity_enabled = init_state["reference_parity_enabled"]
        self.system_prompt = init_state["system_prompt"]
        self.native_tool_system_prompt = init_state["native_tool_system_prompt"]
        self._route_client_cache: Dict[str, Any] = {}
        self._route_build_client = build_openai_client
        self._active_stream_session: OpenAIResponsesSession | None = None
        self._active_stream_lock = threading.Lock()

    def register_active_stream_session(self, session: OpenAIResponsesSession | None) -> None:
        with self._active_stream_lock:
            self._active_stream_session = session

    def clear_active_stream_session(self, session: OpenAIResponsesSession | None = None) -> None:
        with self._active_stream_lock:
            if session is not None and self._active_stream_session is not session:
                return
            self._active_stream_session = None

    def interrupt_active_stream(self) -> bool:
        with self._active_stream_lock:
            session = self._active_stream_session
        if session is None:
            return False
        return bool(session.interrupt_active_stream())

    def _chat_route_synthesis(
        self,
        *,
        route_name: str,
        route_config: ProviderConfig,
        timeout: int | None,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> AgentIntent:
        return openai_planner_synthesis_helpers.chat_route_synthesis(
            self,
            route_name=route_name,
            route_config=route_config,
            timeout=timeout,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
            call_with_provider_retries_fn=call_with_provider_retries,
            timeline_debug_enabled_fn=timeline_debug_enabled,
            log_timeline_fn=log_timeline,
            json_ready_fn=json_ready,
        )

    def _chat_route_followup(
        self,
        *,
        route_name: str,
        route_config: ProviderConfig,
        timeout: int | None,
        user_text: str,
        executed_events: List[ToolEvent],
        tool_executor: PlannerToolExecutor,
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> AgentIntent:
        return openai_planner_coordination_runtime_helpers.chat_route_followup(
            self,
            route_name=route_name,
            route_config=route_config,
            timeout=timeout,
            user_text=user_text,
            executed_events=executed_events,
            tool_executor=tool_executor,
            executed_item_events=executed_item_events,
            attachments=attachments,
            turn_engine_cls=TurnEngine,
            build_tool_followup_initial_input_fn=openai_planner_class_runtime_helpers.build_tool_followup_initial_input,
        )

    def _fresh_synthesis_after_tool_loop(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> AgentIntent:
        return openai_planner_loop_runtime_helpers.fresh_synthesis_after_tool_loop(
            self,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
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
        return openai_planner_loop_runtime_helpers.merge_followup_synthesis_intent(
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
        return openai_planner_loop_runtime_helpers.tool_followup_messages(
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
        return openai_planner_loop_runtime_helpers.fresh_followup_after_tool_loop(
            self,
            user_text=user_text,
            executed_events=executed_events,
            tool_executor=tool_executor,
            executed_item_events=executed_item_events,
            attachments=attachments,
            log_responses_request_fn=_log_responses_request,
            log_responses_response_fn=_log_responses_response,
        )

    def _collect_stream_text(self, **kwargs: Any) -> str:
        return openai_planner_loop_runtime_helpers.collect_stream_text(
            self,
            kwargs=kwargs,
            call_with_provider_retries_fn=call_with_provider_retries,
            attach_responses_503_risks_fn=lambda exc, request_kwargs: attach_responses_503_risks(
                exc,
                request_kwargs,
                source="openai_planner.collect_stream_text",
            ),
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
        return openai_planner_loop_runtime_helpers.synthesis_messages(
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
        initial_send_error: Optional[Exception] = None,
        terminal_handler: Optional[Callable[..., AgentIntent]] = None,
        turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentIntent:
        return openai_planner_loop_runtime_helpers.resume_native_tool_followup(
            self,
            session=session,
            user_text=user_text,
            tool_executor=tool_executor,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            previous_response_id=previous_response_id,
            continuation_input_items=continuation_input_items,
            initial_send_error=initial_send_error,
            terminal_handler=terminal_handler,
            turn_event_callback=turn_event_callback,
            turn_engine_cls=TurnEngine,
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
        provider_session_id: Optional[str] = None,
        provider_turn_id: Optional[str] = None,
        provider_sandbox_mode: Optional[str] = None,
        initial_previous_response_id: Optional[str] = None,
    ) -> AgentIntent:
        return openai_planner_class_runtime_helpers.plan(
            self,
            user_text,
            history,
            tool_executor=tool_executor,
            attachments=attachments,
            input_items=input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            provider_session_id=provider_session_id,
            provider_turn_id=provider_turn_id,
            provider_sandbox_mode=provider_sandbox_mode,
            initial_previous_response_id=initial_previous_response_id,
            plan_with_native_tools_fn=openai_planner_runtime_helpers.plan_with_native_tools,
            responses_session_cls=OpenAIResponsesSession,
            turn_engine_cls=TurnEngine,
        )
