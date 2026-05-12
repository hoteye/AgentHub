from __future__ import annotations

from dataclasses import replace
import time
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.core.turn_engine_facade_runtime import structured_tool_fallback_text
from cli.agent_cli.models import AgentIntent, ToolEvent, default_response_items, response_items_to_text
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.interaction_contract_runtime import resolved_interaction_contract_for_config
from cli.agent_cli.providers.interaction_profile_config import resolve_configured_interaction_profile


def resolved_anthropic_interaction_contract(config: ProviderConfig) -> ResolvedInteractionContract:
    explicit_profile = str(config.interaction_profile or "").strip()
    if explicit_profile:
        return resolved_interaction_contract_for_config(config)

    inferred_profile, _inferred_source = resolve_configured_interaction_profile(
        raw_model=dict(config.raw_model or {}),
        raw_provider=dict(config.raw_provider or {}),
    )
    if str(inferred_profile or "").strip():
        return resolved_interaction_contract_for_config(config)

    seeded_config = replace(
        config,
        interaction_profile="claude_code",
        interaction_profile_source="planner.anthropic_default",
    )
    return resolved_interaction_contract_for_config(seeded_config)


def tool_synthesis_prompt(user_text: str) -> str:
    return (
        "基于上面已经收集到的工具结果，直接回答用户原始问题："
        f"{str(user_text or '').strip()}\n\n"
        "不要继续搜索，不要调用任何工具。"
        "如果用户是在问某个工具怎么用，或者要求示范，请把你刚才实际使用的工具名和关键参数当作简短示例写出来，不要只讲抽象区别。"
        "如果现有证据不足，请明确说明不足点，并给出当前能确认的结论。"
    ).strip()


def terminal_tool_intent(
    *,
    session: Any,
    followup_user_text: str,
    executed_events: List[ToolEvent],
    continuation_input_items: Optional[List[Dict[str, Any]]],
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]],
) -> AgentIntent:
    normalized_input = [
        dict(item)
        for item in list(continuation_input_items or [])
        if isinstance(item, dict)
    ]
    executed_tool_events = list(executed_events or [])

    if normalized_input:
        synthesis_input = [
            *normalized_input,
            {
                "type": "message",
                "role": "user",
                "content": tool_synthesis_prompt(followup_user_text),
            },
        ]
        synthesis_started_at = time.perf_counter()
        try:
            response = session.send(
                input_items=synthesis_input,
                allow_tools=False,
                turn_event_callback=turn_event_callback,
            )
            assistant_text = str(response.output_text or "").strip()
            if not assistant_text and response.response_items:
                assistant_text = response_items_to_text(list(response.response_items or [])).strip()
            if assistant_text:
                response_items = list(
                    response.response_items or default_response_items(assistant_text=assistant_text)
                )
                elapsed_ms = int((time.perf_counter() - synthesis_started_at) * 1000)
                timings = {
                    "initial_model_ms": 0,
                    "tool_execution_ms": 0,
                    "synthesis_model_ms": elapsed_ms,
                    "total_ms": elapsed_ms,
                    "planning_rounds": 0,
                    "synthesis_rounds": 1,
                    "tool_call_count": len(executed_tool_events),
                }
                usage = response.trace.get("usage") if isinstance(getattr(response, "trace", None), dict) else None
                if isinstance(usage, dict):
                    timings["token_usage"] = dict(usage)
                return AgentIntent(
                    assistant_text=assistant_text,
                    response_items=response_items,
                    command_text=None,
                    status_hint="tool",
                    tool_events=executed_tool_events,
                    timings=timings,
                )
        except Exception:
            pass

    assistant_text = structured_tool_fallback_text(executed_tool_events) or "模型未返回内容。"
    response_items = default_response_items(assistant_text=assistant_text)
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=executed_tool_events,
    )
