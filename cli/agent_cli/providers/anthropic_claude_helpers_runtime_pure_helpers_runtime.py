from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional


def stable_tool_specs_payload(tool_specs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], str]:
    normalized = [dict(spec) for spec in list(tool_specs or []) if isinstance(spec, dict)]
    if not normalized:
        return [], ""
    fingerprint = hashlib.sha1(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return normalized, fingerprint


def history_for_conversation(
    history: List[Dict[str, str]],
    *,
    input_items: Optional[List[Dict[str, Any]]],
    input_items_have_assistant_turn_fn: Callable[[Optional[List[Dict[str, Any]]]], bool],
) -> List[Dict[str, str]]:
    if input_items_have_assistant_turn_fn(input_items):
        return []
    return list(history or [])


def command_builder(
    *,
    host_platform: Any,
    plugin_manager_factory: Any,
    command_for_tool_call_fn: Callable[..., Optional[str]],
) -> Callable[[str, Dict[str, Any]], Optional[str]]:
    return lambda name, arguments: command_for_tool_call_fn(
        name,
        arguments,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )


__all__ = [
    "command_builder",
    "history_for_conversation",
    "stable_tool_specs_payload",
]
