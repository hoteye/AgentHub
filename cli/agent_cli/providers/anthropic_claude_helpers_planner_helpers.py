from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent, default_response_items, response_items_to_text
from cli.agent_cli.providers import anthropic_claude_helpers_planner_runtime as anthropic_claude_helpers_planner_runtime_service
from cli.agent_cli.providers import anthropic_claude_helpers_projection_runtime as anthropic_claude_helpers_projection_runtime_service
from cli.agent_cli.providers import anthropic_claude_helpers_runtime as anthropic_claude_helpers_runtime_service
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool
from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.system_prompts import build_chat_completions_system_prompt
from cli.agent_cli.providers.tool_specs import resolve_native_web_search_capability

PluginManagerFactory = Callable[[], Optional[PluginManager]]


@dataclass(frozen=True)
class AnthropicPlannerInitState:
    client: Any
    raw_model: Dict[str, Any]
    supports_tools: bool
    use_native_web_search: bool
    use_native_web_search_main_loop: bool
    max_tokens: int
    system_prompt: str


def resolved_anthropic_interaction_contract(config: ProviderConfig) -> ResolvedInteractionContract:
    return anthropic_claude_helpers_planner_runtime_service.resolved_anthropic_interaction_contract(config)


def apply_interaction_profile_defaults(
    *,
    config: ProviderConfig,
    resolved_interaction_contract: ResolvedInteractionContract,
) -> None:
    if str(config.interaction_profile or "").strip():
        return
    config.interaction_profile = str(resolved_interaction_contract.profile or "").strip()
    config.interaction_profile_source = str(resolved_interaction_contract.source or "").strip()


def build_planner_init_state(
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
    plugin_manager_factory: PluginManagerFactory | None,
    build_anthropic_client_fn: Callable[[ProviderConfig], Any],
    default_max_tokens: int,
) -> AnthropicPlannerInitState:
    raw_model = dict(config.raw_model or {})
    native_web_search_capability = resolve_native_web_search_capability(config)
    use_native_web_search_main_loop = bool(native_web_search_capability.main_loop_spec_kind == "anthropic_native")
    return AnthropicPlannerInitState(
        client=build_anthropic_client_fn(config),
        raw_model=raw_model,
        supports_tools=optional_bool(raw_model.get("supports_tools"), True),
        use_native_web_search=bool(native_web_search_capability.supports_runtime_native),
        use_native_web_search_main_loop=use_native_web_search_main_loop,
        max_tokens=int(raw_model.get("max_output_tokens") or raw_model.get("max_tokens") or default_max_tokens),
        system_prompt=build_chat_completions_system_prompt(
            host_platform=host_platform,
            use_native_web_search=use_native_web_search_main_loop,
            config=config,
            plugin_manager_factory=plugin_manager_factory,
        ),
    )


def history_for_conversation(
    history: List[Dict[str, str]],
    *,
    input_items: Optional[List[Dict[str, Any]]],
    input_items_have_assistant_turn_fn: Callable[[List[Dict[str, Any]]], bool],
) -> List[Dict[str, str]]:
    return anthropic_claude_helpers_runtime_service.history_for_conversation(
        history,
        input_items=input_items,
        input_items_have_assistant_turn_fn=input_items_have_assistant_turn_fn,
    )


def build_session(
    *,
    session_factory: Callable[..., Any],
    client: Any,
    model: str,
    system_prompt: str,
    tool_specs: List[Dict[str, Any]],
    max_tokens: int,
    supports_tools: bool,
    tool_result_projection_policy: str,
    thread_id: str | None,
    workspace_root: str | None,
) -> Any:
    return session_factory(
        client=client,
        model=model,
        system_prompt=system_prompt,
        tool_specs=tool_specs,
        max_tokens=max_tokens,
        supports_tools=supports_tools,
        tool_result_projection_policy=str(tool_result_projection_policy or "").strip(),
        tool_output_thread_id=str(thread_id or "").strip() or None,
        workspace_root=str(workspace_root or "").strip() or None,
    )


def plan_without_tools(
    *,
    user_text: str,
    history: List[Dict[str, str]],
    attachments: Optional[List[PromptAttachment]],
    input_items: Optional[List[Dict[str, Any]]],
    build_session_fn: Callable[..., Any],
    conversation_input_items_fn: Callable[..., List[Dict[str, Any]]],
    history_for_conversation_fn: Callable[..., List[Dict[str, str]]],
) -> AgentIntent:
    return anthropic_claude_helpers_runtime_service.plan_without_tools(
        user_text=user_text,
        history=history,
        attachments=attachments,
        input_items=input_items,
        build_session_fn=build_session_fn,
        conversation_input_items_fn=conversation_input_items_fn,
        history_for_conversation_fn=history_for_conversation_fn,
        response_items_to_text_fn=response_items_to_text,
        default_response_items_fn=default_response_items,
        agent_intent_factory=AgentIntent,
    )


def plan(
    *,
    user_text: str,
    history: List[Dict[str, str]],
    tool_executor: Optional[Callable[[str], Any]],
    attachments: Optional[List[PromptAttachment]],
    input_items: Optional[List[Dict[str, Any]]],
    prompt_cache_key: Optional[str],
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]],
    pending_input_items_getter: Optional[Callable[..., List[Dict[str, Any]]]],
    supports_tools: bool,
    plan_without_tools_fn: Callable[..., AgentIntent],
    conversation_input_items_fn: Callable[..., List[Dict[str, Any]]],
    history_for_conversation_fn: Callable[..., List[Dict[str, str]]],
    build_session_fn: Callable[..., Any],
    host_platform: HostPlatform,
    plugin_manager_factory: PluginManagerFactory | None,
    command_for_tool_call_fn: Callable[..., Optional[str]],
    turn_engine_cls: Callable[..., Any],
    max_rounds: int,
) -> AgentIntent:
    if tool_executor is None or not supports_tools:
        return plan_without_tools_fn(
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )

    messages = conversation_input_items_fn(
        user_text,
        history_for_conversation_fn(history, input_items=input_items),
        attachments=attachments,
        input_items=input_items,
    )
    session = build_session_fn(thread_id=str(prompt_cache_key or "").strip() or None)

    def _terminal_handler(
        followup_user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        _previous_response_id: Optional[str] = None,
        continuation_input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentIntent:
        del executed_item_events, _previous_response_id
        return anthropic_claude_helpers_planner_runtime_service.terminal_tool_intent(
            session=session,
            followup_user_text=followup_user_text,
            executed_events=executed_events,
            continuation_input_items=continuation_input_items,
            turn_event_callback=turn_event_callback,
        )

    engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=anthropic_claude_helpers_runtime_service.command_builder(
            host_platform=host_platform,
            plugin_manager_factory=plugin_manager_factory,
            command_for_tool_call_fn=command_for_tool_call_fn,
        ),
        followup_handler=_terminal_handler,
        terminal_handler=_terminal_handler,
        turn_event_callback=turn_event_callback,
        pending_input_items_getter=pending_input_items_getter,
        max_rounds=max_rounds,
    )
    return anthropic_claude_helpers_projection_runtime_service.with_tool_demo_examples(
        engine.run(
            user_text=user_text,
            initial_input=messages,
            prompt_cache_key=str(prompt_cache_key or "").strip() or None,
        ),
        user_text=user_text,
    )
