from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.core.provider_session import (
    ProviderSession,
    ProviderSessionResult,
    ProviderToolCall,
)
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers import anthropic_claude_helpers_build_client as build_client_helpers
from cli.agent_cli.providers import anthropic_claude_helpers_planner_helpers as planner_helpers
from cli.agent_cli.providers import anthropic_claude_helpers_session_helpers as session_helpers
from cli.agent_cli.providers import anthropic_claude_helpers_stateless as stateless_helpers
from cli.agent_cli.providers import (
    anthropic_claude_session_runtime_normalization_helpers_runtime as normalization_helpers,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.planners_common import BasePlanner
from cli.agent_cli.workspace_context import render_workspace_reference_context_item_message

runtime_helpers = stateless_helpers.runtime_helpers
DEFAULT_CLAUDE_MODEL = stateless_helpers.DEFAULT_CLAUDE_MODEL
DEFAULT_MAX_TOKENS = stateless_helpers.DEFAULT_MAX_TOKENS
ANTHROPIC_TURN_ENGINE_MAX_ROUNDS = stateless_helpers.ANTHROPIC_TURN_ENGINE_MAX_ROUNDS
CLAUDE_PROVIDER_ALIASES = stateless_helpers.CLAUDE_PROVIDER_ALIASES

PlannerToolExecutor = Callable[[str], tuple[str, list[ToolEvent]]]
PluginManagerFactory = Callable[[], PluginManager | None]

_log_anthropic_request = stateless_helpers.log_anthropic_request
_log_anthropic_response = stateless_helpers.log_anthropic_response
_message_text = stateless_helpers.message_text
ClaudeConfigPaths = stateless_helpers.ClaudeConfigPaths
claude_config_paths = stateless_helpers.claude_config_paths
_function_fields_from_spec = stateless_helpers.function_fields_from_spec
anthropic_tool_specs = stateless_helpers.anthropic_tool_specs
_quote_arg = stateless_helpers.quote_arg
_command_for_tool_call = stateless_helpers.command_for_tool_call


def should_use_claude_provider(
    *,
    env_mapping: Mapping[str, str],
    configured_provider: str = "",
    configured_model: str = "",
    selected_config: ProviderConfig | None = None,
) -> bool:
    return stateless_helpers.should_use_claude_provider(
        env_mapping=env_mapping,
        configured_provider=configured_provider,
        configured_model=configured_model,
        selected_config=selected_config,
        claude_provider_aliases=CLAUDE_PROVIDER_ALIASES,
    )


def load_claude_provider_config(
    *,
    env_mapping: Mapping[str, str],
    home_dir: Path | None = None,
    config_paths: ClaudeConfigPaths | None = None,
    fallback_model: str = "",
    fallback_base_url: str = "",
) -> ProviderConfig | None:
    return stateless_helpers.load_claude_provider_config(
        env_mapping=env_mapping,
        home_dir=home_dir,
        config_paths=config_paths,
        fallback_model=fallback_model,
        fallback_base_url=fallback_base_url,
        default_claude_model=DEFAULT_CLAUDE_MODEL,
        default_max_tokens=DEFAULT_MAX_TOKENS,
    )


def build_anthropic_client(config: ProviderConfig) -> Any:
    return build_client_helpers.build_anthropic_client(config)


_content_block_dict = stateless_helpers.content_block_dict


def _resolved_anthropic_interaction_contract(config: ProviderConfig) -> ResolvedInteractionContract:
    return planner_helpers.resolved_anthropic_interaction_contract(config)


def _pending_tool_use_ids_from_messages(messages: list[dict[str, Any]]) -> set[str]:
    return stateless_helpers.pending_tool_use_ids_from_messages(messages)


@dataclass
class AnthropicMessagesSession(ProviderSession):
    client: Any
    model: str
    system_prompt: str
    tool_specs: list[dict[str, Any]]
    max_tokens: int = DEFAULT_MAX_TOKENS
    supports_tools: bool = True
    create_fn: Callable[..., Any] | None = None
    stream_fn: Callable[..., Any] | None = None
    tool_result_projection_policy: str = ""
    tool_output_thread_id: str | None = None
    workspace_root: str | None = None
    _messages: list[dict[str, Any]] = field(default_factory=list)
    _response_count: int = 0
    _cached_tool_specs_payload: list[dict[str, Any]] | None = None
    _cached_tool_specs_fingerprint: str = ""
    _tool_specs_cache_hits: int = 0

    @classmethod
    def _tool_result_block(
        cls,
        *,
        call_id: str,
        output: Any,
        success: bool | None,
    ) -> dict[str, Any]:
        return session_helpers.tool_result_block(
            call_id=call_id,
            output=output,
            success=success,
        )

    @classmethod
    def _normalize_messages(
        cls,
        input_items: list[dict[str, Any]],
        *,
        known_tool_use_ids: set[str] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        return normalization_helpers.normalize_messages(
            input_items,
            tool_result_block_fn=cls._tool_result_block,
            message_text_fn=_message_text,
            workspace_reference_message_fn=render_workspace_reference_context_item_message,
            timeline_debug_enabled_fn=timeline_debug_enabled,
            log_timeline_fn=log_timeline,
            json_ready_fn=json_ready,
            known_tool_use_ids=known_tool_use_ids,
        )

    @staticmethod
    def _content_text(content: Any) -> str:
        return session_helpers.content_text(
            content=content,
            content_block_dict_fn=_content_block_dict,
        )

    @staticmethod
    def _assistant_message(content: Any) -> dict[str, Any]:
        return session_helpers.assistant_message(
            content=content,
            content_block_dict_fn=_content_block_dict,
        )

    @staticmethod
    def _tool_calls(content: Any) -> list[ProviderToolCall]:
        return session_helpers.tool_calls(
            content=content,
            content_block_dict_fn=_content_block_dict,
        )

    def _request_tool_specs(self) -> tuple[list[dict[str, Any]], str, bool]:
        return session_helpers.request_tool_specs_payload(self)

    def _resolve_stream_fn(self) -> Callable[..., Any] | None:
        return session_helpers.resolve_stream_fn(
            client=self.client,
            stream_fn=self.stream_fn,
        )

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool = True,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ProviderSessionResult:
        del previous_response_id
        known_tool_use_ids = _pending_tool_use_ids_from_messages(self._messages)

        def _normalize_with_session_context(
            items: list[dict[str, Any]],
        ) -> tuple[list[str], list[dict[str, Any]]]:
            return self._normalize_messages(
                items,
                known_tool_use_ids=known_tool_use_ids,
            )

        return session_helpers.send(
            self,
            input_items=input_items,
            allow_tools=allow_tools,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            default_max_tokens=DEFAULT_MAX_TOKENS,
            normalize_messages_fn=_normalize_with_session_context,
            content_text_fn=self._content_text,
            tool_calls_fn=self._tool_calls,
            assistant_message_fn=self._assistant_message,
            content_block_dict_fn=_content_block_dict,
            log_request_fn=_log_anthropic_request,
            log_response_fn=_log_anthropic_response,
        )

    def build_tool_result_items(
        self,
        *,
        call_id: str,
        command_text: str | None,
        assistant_text: str,
        events: list[ToolEvent],
    ) -> list[dict[str, Any]]:
        return session_helpers.build_tool_result_items(
            call_id=call_id,
            command_text=command_text,
            assistant_text=assistant_text,
            events=events,
            tool_result_projection_policy=self.tool_result_projection_policy,
            workspace_root=self.workspace_root,
            tool_output_thread_id=self.tool_output_thread_id,
        )


class AnthropicClaudePlanner(BasePlanner):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        host_platform: HostPlatform | None = None,
        cwd: str | None = None,
        plugin_manager_factory: PluginManagerFactory | None = None,
    ) -> None:
        super().__init__(
            config,
            host_platform=host_platform,
            cwd=cwd,
            plugin_manager_factory=plugin_manager_factory,
        )
        self.resolved_interaction_contract = _resolved_anthropic_interaction_contract(config)
        planner_helpers.apply_interaction_profile_defaults(
            config=self.config,
            resolved_interaction_contract=self.resolved_interaction_contract,
        )
        planner_state = planner_helpers.build_planner_init_state(
            config=self.config,
            host_platform=self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
            build_anthropic_client_fn=build_anthropic_client,
            default_max_tokens=DEFAULT_MAX_TOKENS,
        )
        self.client = planner_state.client
        self.raw_model = planner_state.raw_model
        self.supports_tools = planner_state.supports_tools
        self.use_native_web_search = planner_state.use_native_web_search
        self.use_native_web_search_main_loop = planner_state.use_native_web_search_main_loop
        self.max_tokens = planner_state.max_tokens
        self.system_prompt = planner_state.system_prompt

    def _history_for_conversation(
        self,
        history: list[dict[str, str]],
        *,
        input_items: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        return planner_helpers.history_for_conversation(
            history,
            input_items=input_items,
            input_items_have_assistant_turn_fn=self._input_items_have_assistant_turn,
        )

    def _tool_specs(self) -> list[dict[str, Any]]:
        return anthropic_tool_specs(
            self.config,
            self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def _build_session(self, *, thread_id: str | None = None) -> AnthropicMessagesSession:
        return planner_helpers.build_session(
            session_factory=AnthropicMessagesSession,
            client=self.client,
            model=self.config.model,
            system_prompt=self.system_prompt,
            tool_specs=self._tool_specs(),
            max_tokens=self.max_tokens,
            supports_tools=self.supports_tools,
            tool_result_projection_policy=self.resolved_interaction_contract.tool_result_projection_policy,
            thread_id=thread_id,
            workspace_root=self.cwd,
        )

    def _plan_without_tools(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        attachments: list[PromptAttachment] | None = None,
        input_items: list[dict[str, Any]] | None = None,
    ) -> AgentIntent:
        return planner_helpers.plan_without_tools(
            user_text=user_text,
            history=history,
            attachments=attachments,
            input_items=input_items,
            build_session_fn=self._build_session,
            conversation_input_items_fn=self._conversation_input_items,
            history_for_conversation_fn=self._history_for_conversation,
        )

    def plan(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        tool_executor: PlannerToolExecutor | None = None,
        attachments: list[PromptAttachment] | None = None,
        input_items: list[dict[str, Any]] | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
        pending_input_items_getter: Callable[..., list[dict[str, Any]]] | None = None,
        subagent_type: str | None = None,
    ) -> AgentIntent:
        profile_system_prompt = builtin_agent_profiles_runtime.profile_system_prompt(subagent_type)
        stripped_input_items = builtin_agent_profiles_runtime.without_profile_instruction_items(
            input_items,
            subagent_type=subagent_type,
        )
        if builtin_agent_profiles_runtime.profile_disallows_tool(subagent_type, "Agent"):
            effective_input_items = stripped_input_items
        else:
            effective_input_items = builtin_agent_profiles_runtime.with_agent_listing_input_item(
                stripped_input_items,
                tool_surface_profile=self.resolved_interaction_contract.tool_surface_profile,
            )

        def _build_profiled_session(*, thread_id: str | None = None) -> AnthropicMessagesSession:
            session = self._build_session(thread_id=thread_id)
            if profile_system_prompt:
                session.system_prompt = profile_system_prompt
            session.tool_specs = builtin_agent_profiles_runtime.filter_tool_specs_for_profile(
                getattr(session, "tool_specs", []),
                subagent_type=subagent_type,
            )
            return session

        return planner_helpers.plan(
            user_text=user_text,
            history=history,
            tool_executor=tool_executor,
            attachments=attachments,
            input_items=effective_input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            pending_input_items_getter=pending_input_items_getter,
            supports_tools=self.supports_tools,
            plan_without_tools_fn=self._plan_without_tools,
            conversation_input_items_fn=self._conversation_input_items,
            history_for_conversation_fn=self._history_for_conversation,
            build_session_fn=_build_profiled_session,
            host_platform=self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
            command_for_tool_call_fn=_command_for_tool_call,
            turn_engine_cls=TurnEngine,
            max_rounds=ANTHROPIC_TURN_ENGINE_MAX_ROUNDS,
        )
