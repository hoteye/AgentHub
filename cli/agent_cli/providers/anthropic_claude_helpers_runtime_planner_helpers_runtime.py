from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, PromptAttachment


def plan_without_tools(
    *,
    user_text: str,
    history: List[Dict[str, str]],
    attachments: Optional[List[PromptAttachment]],
    input_items: Optional[List[Dict[str, Any]]],
    build_session_fn: Callable[[], Any],
    conversation_input_items_fn: Callable[..., List[Dict[str, Any]]],
    history_for_conversation_fn: Callable[..., List[Dict[str, str]]],
    response_items_to_text_fn: Callable[[List[Dict[str, Any]]], str],
    default_response_items_fn: Callable[..., List[Dict[str, Any]]],
    agent_intent_factory: Callable[..., AgentIntent],
) -> AgentIntent:
    started_at = time.perf_counter()
    session = build_session_fn()
    messages = conversation_input_items_fn(
        user_text,
        history_for_conversation_fn(history, input_items=input_items),
        attachments=attachments,
        input_items=input_items,
    )
    response = session.send(input_items=messages, allow_tools=False)
    assistant_text = str(response.output_text or "").strip()
    if not assistant_text and response.response_items:
        assistant_text = response_items_to_text_fn(list(response.response_items or [])).strip()
    if not assistant_text:
        assistant_text = "模型未返回内容。"
    response_items = list(response.response_items or default_response_items_fn(assistant_text=assistant_text))
    timings = {
        "initial_model_ms": int((time.perf_counter() - started_at) * 1000),
        "tool_execution_ms": 0,
        "synthesis_model_ms": 0,
        "total_ms": int((time.perf_counter() - started_at) * 1000),
        "planning_rounds": 1,
        "synthesis_rounds": 0,
        "tool_call_count": 0,
    }
    usage = response.trace.get("usage") if isinstance(getattr(response, "trace", None), dict) else None
    if isinstance(usage, dict):
        timings["token_usage"] = dict(usage)
    return agent_intent_factory(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="assistant",
        timings=timings,
    )


__all__ = ["plan_without_tools"]
