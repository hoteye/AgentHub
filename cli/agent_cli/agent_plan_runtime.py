from __future__ import annotations

import shlex
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.runtime_core.command_dispatch import tool_result_fallback_text
from cli.agent_cli.runtime_core.local_routing import (
    extract_first_url,
    live_web_query_text,
)


def host_shell_alias_intent(
    text: str,
    normalized: str,
    *,
    host_platform: HostPlatform,
) -> AgentIntent | None:
    if not (normalized.startswith("shell ") or normalized.startswith("cmd ")):
        return None
    command = text.split(" ", 1)[1].strip() if " " in text else ""
    return AgentIntent(
        assistant_text="识别为 shell 请求，准备执行。",
        command_text=host_platform.shell_command(command),
        status_hint="tool",
    )


def planner_call_kwargs(
    planner: Any,
    *,
    filter_callable_kwargs: Callable[[Callable[..., Any], Dict[str, Any]], Dict[str, Any]],
    tool_executor: Optional[Callable[[str], Tuple[str, List[ToolEvent]]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    input_items: Optional[List[Dict[str, Any]]] = None,
    prompt_cache_key: Optional[str] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    provider_session_id: Optional[str] = None,
    provider_turn_id: Optional[str] = None,
    provider_sandbox_mode: Optional[str] = None,
    initial_previous_response_id: Optional[str] = None,
) -> Dict[str, Any]:
    return filter_callable_kwargs(
        planner.plan,
        {
            "tool_executor": tool_executor,
            "attachments": attachments or [],
            "input_items": input_items or [],
            "prompt_cache_key": prompt_cache_key,
            "turn_event_callback": turn_event_callback,
            "provider_session_id": provider_session_id,
            "provider_turn_id": provider_turn_id,
            "provider_sandbox_mode": provider_sandbox_mode,
            "initial_previous_response_id": initial_previous_response_id,
        },
    )


def planner_is_replay_runtime(planner: Any) -> bool:
    if planner is None:
        return False
    public_summary = getattr(planner, "public_summary", None)
    if not callable(public_summary):
        return False
    try:
        summary = dict(public_summary() or {})
    except Exception:
        return False
    return (
        str(summary.get("planner_kind") or "").strip() == "runtime_replay"
        or str(summary.get("source") or "").strip() == "replay_cassette"
    )


def live_web_fallback_intent(
    text: str,
    *,
    tool_executor: Optional[Callable[[str], Tuple[str, List[ToolEvent]]]],
    summarize_live_web_result: Callable[[str, ToolEvent], str],
) -> AgentIntent | None:
    if tool_executor is None:
        return None
    explicit_url = extract_first_url(text)
    if explicit_url:
        _, events = tool_executor(f"/web_fetch {shlex.quote(explicit_url)}")
        if events:
            return AgentIntent(
                commentary_text="这是实时信息查询，我先读取网页。",
                assistant_text=tool_result_fallback_text(events),
                tool_events=events,
                status_hint="tool",
            )
    query = live_web_query_text(text)
    if not query:
        return None
    _, events = tool_executor(f"/web_search {query}")
    if not events:
        return None
    web_event = next((event for event in events if event.name == "web_search"), events[-1])
    return AgentIntent(
        commentary_text="这是实时信息查询，我先做网页搜索。",
        assistant_text=summarize_live_web_result(query, web_event),
        tool_events=events,
        status_hint="tool",
    )
