from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.delegation_policy import planner_tool_execution_target
from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.interaction_contract_runtime import resolved_interaction_contract_for_config


PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def reference_parity_enabled_for_contract(contract: ResolvedInteractionContract) -> bool:
    if _normalized(getattr(contract, "profile", "")) == "codex_openai":
        return True
    if _normalized(getattr(contract, "base_prompt_profile", "")) == "codex_openai":
        return True
    if _normalized(getattr(contract, "tool_surface_profile", "")) == "codex_openai":
        return True
    return _normalized(getattr(contract, "turn_protocol_policy", "")) == "openai_responses_items"


def planner_init_state(
    *,
    config: ProviderConfig,
    host_platform: Any,
    plugin_manager_factory: Optional[Callable[[], Any]],
    command_text_patterns_fn: Callable[..., tuple[Any, Any]],
    provider_tool_names_fn: Callable[..., List[str]],
    minimal_provider_tool_names_fn: Callable[..., List[str]],
    build_json_system_prompt_fn: Callable[..., str],
    build_native_system_prompt_fn: Callable[..., str],
) -> dict[str, Any]:
    command_pattern, followup_command_pattern = command_text_patterns_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )
    available_tool_names = ", ".join(
        provider_tool_names_fn(
            config,
            host_platform,
            plugin_manager_factory=plugin_manager_factory,
        )
    )
    native_available_tool_names = ", ".join(
        minimal_provider_tool_names_fn(
            config,
            host_platform,
            plugin_manager_factory=plugin_manager_factory,
        )
    )
    resolved_contract = resolved_interaction_contract_for_config(config)
    reference_parity = reference_parity_enabled_for_contract(resolved_contract)
    return {
        "command_pattern": command_pattern,
        "followup_command_pattern": followup_command_pattern,
        "resolved_interaction_contract": resolved_contract,
        "reference_parity_enabled": reference_parity,
        "system_prompt": build_json_system_prompt_fn(
            host_platform=host_platform,
            available_tool_names=available_tool_names,
            plugin_manager_factory=plugin_manager_factory,
            config=config,
        ),
        "native_tool_system_prompt": build_native_system_prompt_fn(
            host_platform=host_platform,
            available_tool_names=native_available_tool_names,
            config=config,
        ),
    }


def build_tool_followup_initial_input(
    *,
    system_prompt: str,
    followup_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        {"role": "system", "content": system_prompt},
        *followup_messages,
    ]


def command_for_function_call(
    *,
    name: str,
    arguments: Dict[str, Any],
    host_platform: Any,
    plugin_manager_factory: Optional[Callable[[], Any]],
    optional_bool_fn: Callable[[Any, bool], bool],
    quote_arg_fn: Callable[[Any], str],
    command_for_tool_call_fn: Callable[..., Optional[str]],
) -> Optional[str]:
    effective_name, enriched_arguments = planner_tool_execution_target(name, arguments)
    return command_for_tool_call_fn(
        effective_name,
        enriched_arguments,
        host_platform,
        optional_bool_fn=optional_bool_fn,
        quote_arg_fn=quote_arg_fn,
        plugin_manager_factory=plugin_manager_factory,
    )


def plan(
    planner: Any,
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
    plan_with_native_tools_fn: Callable[..., AgentIntent],
    responses_session_cls: type[Any],
    turn_engine_cls: type[Any],
) -> AgentIntent:
    if tool_executor is None:
        if planner.reference_parity_enabled:
            return planner._plan_native_without_tools(
                user_text,
                history,
                attachments=attachments,
                input_items=input_items,
                prompt_cache_key=prompt_cache_key,
                turn_event_callback=turn_event_callback,
                provider_session_id=provider_session_id,
                provider_turn_id=provider_turn_id,
                provider_sandbox_mode=provider_sandbox_mode,
            )
        return planner._plan_without_native_tools(
            user_text,
            history,
            attachments=attachments,
            input_items=input_items,
        )
    return plan_with_native_tools_fn(
        planner,
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
        responses_session_cls=responses_session_cls,
        turn_engine_cls=turn_engine_cls,
    )
