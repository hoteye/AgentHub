from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, ToolEvent, default_response_items, response_items_to_text
from cli.agent_cli.providers.anthropic_claude_helpers import AnthropicMessagesSession, build_anthropic_client
from cli.agent_cli.providers.planner_postprocessing import (
    GENERIC_SYNTHESIS_RULES,
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
)
from cli.scripts.run_multi_llm_live_cases_exec_tool_helpers import RuntimeToolExecutor


def _generic_tool_synthesis_prompt(
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parts = [
        *GENERIC_SYNTHESIS_RULES,
        "",
        "ORIGINAL_USER_REQUEST:",
        str(user_text or "").strip(),
        "",
        "TOOL_RESULT_SUMMARY:",
        "\n".join(generic_tool_event_summary_lines(executed_events)) or "- no tool events",
        "",
        "TOOL_RESULT_CONTEXT_JSON:",
        json.dumps(generic_tool_event_context_blocks(executed_events), ensure_ascii=False, indent=2),
    ]
    item_blocks = executed_item_event_context_blocks(executed_item_events or [])
    if item_blocks:
        parts.extend(
            [
                "",
                "EXECUTED_ITEM_EVENTS_JSON:",
                json.dumps(item_blocks, ensure_ascii=False, indent=2),
            ]
        )
    return "\n".join(parts)


def _chat_completion_route_intent(
    planner: Any,
    *,
    route_name: str,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
) -> AgentIntent:
    route = planner._effective_route_resolution(route_name, planner._resolve_route(route_name))
    route_config = route.config or planner.config
    build_messages = getattr(planner, "_synthesis_messages", None)
    if callable(build_messages):
        messages = build_messages(
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=None,
        )
    else:
        messages = [
            {"role": "system", "content": str(getattr(planner, "system_prompt", "") or "").strip()},
            {
                "role": "user",
                "content": _generic_tool_synthesis_prompt(
                    user_text=user_text,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                ),
            },
        ]
    request_kwargs: Dict[str, Any] = {
        "messages": messages,
        "stream": False,
    }
    extra_body_fn = getattr(planner, "_request_extra_body", None)
    if callable(extra_body_fn):
        extra_body = dict(extra_body_fn() or {})
        if extra_body:
            request_kwargs["extra_body"] = extra_body
    response = planner._chat_completion_create(
        client=planner._route_client(route_name, route_config),
        timeout=int(route.timeout or getattr(planner, "model_timeout", 0) or 0) or None,
        model=route_config.model,
        trace_stage=f"chat_completions.route_{route_name}",
        trace_payload={
            "route_name": route_name,
            "route_source": str(route.source or "").strip(),
            "provider_name": str(route_config.provider_name or "").strip(),
            "base_url": str(route_config.base_url or "").strip(),
        },
        **request_kwargs,
    )
    choice = response.choices[0]
    message = choice.message
    content_text_fn = getattr(planner, "_message_content_text", None)
    content_text = (
        content_text_fn(getattr(message, "content", ""))
        if callable(content_text_fn)
        else str(getattr(message, "content", "") or "").strip()
    )
    sanitize_fn = getattr(planner, "_sanitize_final_answer_text", None)
    assistant_text = sanitize_fn(content_text) if callable(sanitize_fn) else str(content_text or "").strip()
    assistant_text = str(assistant_text or "").strip() or "模型未返回内容。"
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=default_response_items(assistant_text=assistant_text),
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
    )


def _anthropic_route_intent(
    planner: Any,
    *,
    route_name: str,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    anthropic_session_cls: Any = AnthropicMessagesSession,
    anthropic_client_builder: Any = build_anthropic_client,
) -> AgentIntent:
    route = planner._effective_route_resolution(route_name, planner._resolve_route(route_name))
    route_config = route.config or planner.config
    session = anthropic_session_cls(
        client=anthropic_client_builder(route_config),
        model=str(route_config.model or "").strip(),
        system_prompt=str(getattr(planner, "system_prompt", "") or "").strip(),
        tool_specs=list(getattr(planner, "_tool_specs", lambda: [])() or []),
        max_tokens=int(getattr(planner, "max_tokens", 0) or 0) or 8192,
        supports_tools=bool(getattr(planner, "supports_tools", True)),
        tool_result_projection_policy=str(
            getattr(getattr(planner, "resolved_interaction_contract", None), "tool_result_projection_policy", "") or ""
        ).strip(),
        workspace_root=str(getattr(planner, "cwd", "") or "").strip() or None,
    )
    response = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": _generic_tool_synthesis_prompt(
                    user_text=user_text,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                ),
            }
        ],
        allow_tools=False,
    )
    assistant_text = str(getattr(response, "output_text", "") or "").strip()
    if not assistant_text:
        assistant_text = response_items_to_text(list(getattr(response, "response_items", []) or [])).strip()
    assistant_text = assistant_text or "模型未返回内容。"
    response_items = list(getattr(response, "response_items", []) or default_response_items(assistant_text=assistant_text))
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
    )


def _planner_case_intent(
    planner: Any,
    *,
    route_name: str,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor: Optional[RuntimeToolExecutor] = None,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    anthropic_session_cls: Any = AnthropicMessagesSession,
    anthropic_client_builder: Any = build_anthropic_client,
) -> AgentIntent:
    if route_name == "tool_followup":
        followup_fn = getattr(planner, "_fresh_followup_after_tool_loop", None)
        if callable(followup_fn):
            return followup_fn(
                user_text=user_text,
                executed_events=executed_events,
                tool_executor=tool_executor,
                executed_item_events=executed_item_events,
            )
    elif route_name == "final_synthesis":
        synthesis_fn = getattr(planner, "_fresh_synthesis_after_tool_loop", None)
        if callable(synthesis_fn):
            return synthesis_fn(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
            )
    route = planner._effective_route_resolution(route_name, planner._resolve_route(route_name))
    route_config = route.config or getattr(planner, "config", None)
    wire_api = str(getattr(route_config, "wire_api", "") or "").strip().lower()
    planner_kind = str(getattr(route_config, "planner_kind", "") or "").strip().lower()
    if wire_api in {"openai_chat", "deepseek_chat"} and callable(getattr(planner, "_chat_completion_create", None)):
        return _chat_completion_route_intent(
            planner,
            route_name=route_name,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
        )
    if wire_api == "anthropic_messages" or planner_kind == "anthropic_messages":
        return _anthropic_route_intent(
            planner,
            route_name=route_name,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            anthropic_session_cls=anthropic_session_cls,
            anthropic_client_builder=anthropic_client_builder,
        )
    plan_fn = getattr(planner, "plan", None)
    if callable(plan_fn):
        return plan_fn(
            _generic_tool_synthesis_prompt(
                user_text=user_text,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
            ),
            [],
            tool_executor=None,
        )
    raise RuntimeError(f"planner does not support route followup path: route={route_name}")
