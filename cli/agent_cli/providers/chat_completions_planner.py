from __future__ import annotations

import json
import re
import shlex
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import (
    ActivityEvent,
    AgentIntent,
    CommandExecutionResult,
    compose_turn_events_from_response_items,
    PromptAttachment,
    ResponseInputItem,
    ToolEvent,
    default_response_items,
    response_items_to_text,
    tool_events_to_turn_events,
)
from cli.agent_cli.providers.adapters.chat_completions import ChatCompletionsSession
from cli.agent_cli.providers.chat_completions_direct_loop import ChatCompletionsDirectLoopMixin
from cli.agent_cli.providers.chat_completions_finalize import ChatCompletionsFinalizeMixin
from cli.agent_cli.providers.chat_completions_protocol import ChatCompletionsProtocolMixin
from cli.agent_cli.providers.chat_completions_synthesis import ChatCompletionsSynthesisMixin
from cli.agent_cli.providers.chat_completions_turn_engine import ChatCompletionsTurnEngineMixin
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool as _optional_bool_impl
from cli.agent_cli.providers.delegation_policy import planner_tool_execution_target
from cli.agent_cli.providers.interaction_contract_runtime import resolved_interaction_contract_for_config
from cli.agent_cli.providers.openai_client import build_openai_client
from cli.agent_cli.providers.policy_grounding import PolicyGroundingMixin
from cli.agent_cli.providers.planners_common import BasePlanner
from cli.agent_cli.providers.system_prompts import build_chat_completions_system_prompt
from cli.agent_cli.providers.policy_routing import looks_like_policy_question as _looks_like_policy_question_impl
from cli.agent_cli.providers.tool_execution_loop import ToolExecutionLoopMixin
from cli.agent_cli.providers.tool_specs import (
    merged_provider_tool_specs as _merged_provider_tool_specs_impl,
    supports_glm_native_web_search as _supports_glm_native_web_search_impl,
)
from cli.agent_cli.providers.tool_calls import (
    command_for_tool_call as _command_for_tool_call_impl,
    tool_result_payload as _tool_result_payload_impl,
)

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def _quote_arg(value: Any) -> str:
    return shlex.quote(str(value))


def _optional_bool(value: Any, default: bool = False) -> bool:
    return _optional_bool_impl(value, default)


def _command_for_tool_call(
    name: str,
    arguments: Dict[str, Any],
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Callable[[], PluginManager | None] | None = None,
) -> Optional[str]:
    effective_name, enriched_arguments = planner_tool_execution_target(name, arguments)
    return _command_for_tool_call_impl(
        effective_name,
        enriched_arguments,
        host_platform,
        optional_bool_fn=_optional_bool,
        quote_arg_fn=_quote_arg,
        plugin_manager_factory=plugin_manager_factory,
    )


def _tool_result_payload(command_text: Optional[str], assistant_text: str, events: List[ToolEvent]) -> Dict[str, Any]:
    return _tool_result_payload_impl(command_text, assistant_text, events)


def _looks_like_policy_question(user_text: str) -> bool:
    return _looks_like_policy_question_impl(user_text)


def _supports_glm_native_web_search(config: ProviderConfig) -> bool:
    return _supports_glm_native_web_search_impl(config)


def _tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Callable[[], PluginManager | None] = PluginManager,
) -> List[Dict[str, Any]]:
    return _merged_provider_tool_specs_impl(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )


class ChatCompletionsPlanner(
    ChatCompletionsDirectLoopMixin,
    ChatCompletionsFinalizeMixin,
    ChatCompletionsProtocolMixin,
    ChatCompletionsSynthesisMixin,
    ChatCompletionsTurnEngineMixin,
    ToolExecutionLoopMixin,
    PolicyGroundingMixin,
    BasePlanner,
):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        host_platform: HostPlatform | None = None,
        cwd: str | None = None,
        plugin_manager_factory: Callable[[], PluginManager | None] | None = None,
    ) -> None:
        super().__init__(
            config,
            host_platform=host_platform,
            cwd=cwd,
            plugin_manager_factory=plugin_manager_factory,
        )
        self.resolved_interaction_contract = resolved_interaction_contract_for_config(config)
        self.interaction_profile = str(self.resolved_interaction_contract.profile or "").strip()
        self.turn_protocol_policy = str(self.resolved_interaction_contract.turn_protocol_policy or "").strip()
        self.client = build_openai_client(
            config,
            fallback_base_url="https://api.deepseek.com",
        )
        self._chat_protocol_build_client = build_openai_client
        self._chat_protocol_timeline_debug_enabled = timeline_debug_enabled
        self._chat_protocol_log_timeline = log_timeline
        self._chat_protocol_json_ready = json_ready
        self._tool_loop_command_for_tool_call = _command_for_tool_call
        self._tool_loop_tool_result_payload = _tool_result_payload
        self._turn_engine_session_cls = ChatCompletionsSession
        self._turn_engine_cls = TurnEngine
        self._turn_engine_tool_specs_builder = _tool_specs
        self._turn_engine_command_builder = _command_for_tool_call
        self._turn_engine_perf_counter_fn = time.perf_counter
        self._direct_loop_tool_specs_builder = _tool_specs
        self._direct_loop_command_builder = _command_for_tool_call
        raw_model = config.raw_model or {}
        self.supports_parallel_tool_calls = _optional_bool(raw_model.get("supports_parallel_tool_calls"), False)
        self.supports_tools = _optional_bool(raw_model.get("supports_tools"), True)
        self.supports_reasoning = _optional_bool(raw_model.get("supports_reasoning"), False) or (
            (config.planner_kind or "").strip().lower() == "deepseek_reasoner"
        ) or ("reasoner" in str(config.model or "").lower())
        self.model_timeout = int(raw_model.get("model_timeout") or (45 if self.supports_reasoning else 30))
        self.policy_llm_assist = _optional_bool(raw_model.get("policy_llm_assist"), self.supports_reasoning)
        self.policy_llm_timeout = int(raw_model.get("policy_llm_timeout") or 20)
        helper_model = str(raw_model.get("policy_llm_helper_model") or "").strip()
        if not helper_model and self.supports_reasoning and "reasoner" in str(config.model or "").lower():
            helper_model = "deepseek-chat"
        self._policy_llm_legacy_helper_model = helper_model or None
        self.policy_llm_helper_model = helper_model or self.config.model
        self.reasoning_mode = str(raw_model.get("reasoning_mode") or "").strip().lower()
        self.reasoning_output_field = str(raw_model.get("reasoning_output_field") or "reasoning_content").strip()
        self._policy_query_rewrite_cache: Dict[str, Dict[str, Any]] = {}
        self._policy_rerank_cache: Dict[str, Dict[str, Any]] = {}
        self._policy_extract_cache: Dict[str, Dict[str, Any]] = {}
        self._route_client_cache: Dict[str, Any] = {}
        self.use_glm_native_web_search = _supports_glm_native_web_search(config)
        self.system_prompt = build_chat_completions_system_prompt(
            host_platform=self.host_platform,
            use_glm_native_web_search=self.use_glm_native_web_search,
            config=self.config,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def plan(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        tool_executor: Optional[PlannerToolExecutor] = None,
        attachments: Optional[List[PromptAttachment]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        started_at = time.perf_counter()
        messages = self._chat_messages(
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )
        executed_events: List[ToolEvent] = []
        executed_item_events: List[Dict[str, Any]] = []
        final_text = ""
        policy_question = _looks_like_policy_question(user_text)
        policy_summary_question = self._policy_is_summary_question(user_text) if policy_question else False
        policy_preflight_before_model = self._policy_should_preflight_before_model(user_text) if policy_question else False
        policy_query_plan = self._policy_query_plan(user_text) if policy_question else []
        skip_direct_planning = False
        initial_model_ms = 0
        tool_execution_ms = 0
        synthesis_model_ms = 0
        planning_rounds = 0
        synthesis_rounds = 0
        planning_trace: List[Dict[str, Any]] = []
        synthesis_trace: List[Dict[str, Any]] = []
        response_items: List[ResponseInputItem] = []
        turn_engine_turn_events: List[Dict[str, Any]] = []
        turn_engine_item_event_count = 0
        turn_engine_final_text = ""

        if tool_executor is not None and policy_preflight_before_model:
            preflight_events, preflight_item_events = self._execute_policy_preflight(
                user_text,
                executed_events,
                executed_item_events,
                tool_executor,
            )
            if preflight_events:
                executed_events.extend(preflight_events)
                executed_item_events.extend(preflight_item_events)
                skip_direct_planning = True

        use_turn_engine = tool_executor is not None

        if not skip_direct_planning:
            if use_turn_engine:
                planning_intent = self._planning_intent_with_turn_engine(
                    user_text=user_text,
                    messages=messages,
                    tool_executor=tool_executor,
                )
                executed_events.extend(list(planning_intent.tool_events or []))
                executed_item_events.extend(
                    self._rebase_item_events(
                        self._tool_item_events_from_turn_events(list(planning_intent.turn_events or [])),
                        start_index=self._next_item_index(executed_item_events),
                    )
                )
                turn_engine_turn_events = [
                    dict(item)
                    for item in list(planning_intent.turn_events or [])
                    if isinstance(item, dict)
                ]
                response_items = list(planning_intent.response_items or [])
                final_text = self._sanitize_final_answer_text(planning_intent.assistant_text)
                if not final_text and response_items:
                    final_text = self._sanitize_final_answer_text(response_items_to_text(response_items))
                turn_engine_item_event_count = len(executed_item_events)
                turn_engine_final_text = final_text
                planning_timings = dict(planning_intent.timings or {})
                initial_model_ms += int(planning_timings.get("initial_model_ms") or 0)
                tool_execution_ms += int(planning_timings.get("tool_execution_ms") or 0)
                planning_rounds += int(planning_timings.get("planning_rounds") or 0)
                planning_trace.extend(list(planning_timings.get("planning_trace") or []))
            else:
                direct_loop = self._run_direct_planning_loop(
                    started_at=started_at,
                    user_text=user_text,
                    messages=messages,
                    tool_executor=tool_executor,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                    initial_model_ms=initial_model_ms,
                    tool_execution_ms=tool_execution_ms,
                    synthesis_model_ms=synthesis_model_ms,
                    planning_rounds=planning_rounds,
                    synthesis_rounds=synthesis_rounds,
                    planning_trace=planning_trace,
                    synthesis_trace=synthesis_trace,
                    perf_counter_fn=time.perf_counter,
                    tool_specs_builder=self._direct_loop_tool_specs_builder,
                    command_builder=self._direct_loop_command_builder,
                )
                immediate_intent = direct_loop.get("immediate_intent")
                if isinstance(immediate_intent, AgentIntent):
                    return immediate_intent
                final_text = str(direct_loop.get("final_text") or "")
                response_items = list(direct_loop.get("response_items") or [])
                initial_model_ms = int(direct_loop.get("initial_model_ms") or 0)
                tool_execution_ms = int(direct_loop.get("tool_execution_ms") or 0)
                planning_rounds = int(direct_loop.get("planning_rounds") or 0)
                planning_trace = [
                    dict(item)
                    for item in list(direct_loop.get("planning_trace") or [])
                    if isinstance(item, dict)
                ]
        return self._finalize_chat_plan(
            started_at=started_at,
            user_text=user_text,
            attachments=attachments,
            tool_executor=tool_executor,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            final_text=final_text,
            policy_question=policy_question,
            policy_summary_question=policy_summary_question,
            policy_query_plan=policy_query_plan,
            initial_model_ms=initial_model_ms,
            tool_execution_ms=tool_execution_ms,
            synthesis_model_ms=synthesis_model_ms,
            planning_rounds=planning_rounds,
            synthesis_rounds=synthesis_rounds,
            planning_trace=planning_trace,
            synthesis_trace=synthesis_trace,
            response_items=response_items,
            turn_engine_turn_events=turn_engine_turn_events,
            turn_engine_item_event_count=turn_engine_item_event_count,
            perf_counter_fn=time.perf_counter,
        )


DeepSeekPlanner = ChatCompletionsPlanner
