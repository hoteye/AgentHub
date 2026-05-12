"""Anthropic request/response logging and diagnostics helpers.

Extracted from anthropic_claude_runtime for cohesion.
"""

from __future__ import annotations

import logging
from typing import Any

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.providers.adapters.openai_responses_output_runtime import (
    json_ready as _json_ready_impl,
)

logger = logging.getLogger(__name__)


def json_ready(value: Any) -> Any:
    return _json_ready_impl(value)


def _count_key(value: Any, key_name: str) -> int:
    if isinstance(value, dict):
        return (1 if key_name in value else 0) + sum(
            _count_key(item, key_name) for item in value.values()
        )
    if isinstance(value, list | tuple):
        return sum(_count_key(item, key_name) for item in value)
    return 0


def _system_summary(system: Any) -> dict[str, Any]:
    if isinstance(system, str):
        return {
            "system_type": "string",
            "system_text_length": len(system),
            "system_block_count": 0,
        }
    if isinstance(system, list):
        text_length = 0
        for block in system:
            if isinstance(block, dict):
                text_length += len(str(block.get("text") or ""))
        return {
            "system_type": "blocks",
            "system_text_length": text_length,
            "system_block_count": len(system),
        }
    return {
        "system_type": type(system).__name__ if system is not None else "none",
        "system_text_length": 0,
        "system_block_count": 0,
    }


def _request_diagnostics(request: dict[str, Any]) -> dict[str, Any]:
    messages = request.get("messages")
    tools = request.get("tools")
    tools_list = tools if isinstance(tools, list) else []
    diagnostics = {
        **_system_summary(request.get("system")),
        "tool_names": [
            str(tool.get("name") or tool.get("type") or "").strip()
            for tool in tools_list
            if isinstance(tool, dict)
        ],
        "betas": (
            list(request.get("betas") or []) if isinstance(request.get("betas"), list) else []
        ),
        "has_thinking": bool(request.get("thinking")),
        "has_metadata": bool(request.get("metadata")),
        "tool_choice": json_ready(request.get("tool_choice")),
        "cache_control_count": _count_key(request, "cache_control"),
        "message_cache_control_count": _count_key(messages, "cache_control"),
        "tool_cache_control_count": _count_key(tools, "cache_control"),
        "system_cache_control_count": _count_key(request.get("system"), "cache_control"),
    }
    return diagnostics


def log_anthropic_request(request: dict[str, Any]) -> None:
    if not timeline_debug_enabled():
        return
    messages = request.get("messages")
    tools = request.get("tools")
    log_timeline(
        "anthropic_messages.request_raw",
        request=json_ready(request),
        message_count=len(messages) if isinstance(messages, list) else 0,
        tool_count=len(tools) if isinstance(tools, list) else 0,
        **_request_diagnostics(request),
    )


def log_anthropic_response(response: Any) -> None:
    if not timeline_debug_enabled():
        return
    content = getattr(response, "content", None)
    log_timeline(
        "anthropic_messages.response_raw",
        response=json_ready(response),
        response_id=str(getattr(response, "id", "") or "").strip() or None,
        content_count=len(content) if isinstance(content, list) else 0,
    )
