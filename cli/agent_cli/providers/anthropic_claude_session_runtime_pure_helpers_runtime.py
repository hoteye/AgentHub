from __future__ import annotations

from typing import Any, Dict, List


def build_request(
    *,
    model: str,
    base_system_prompt: str,
    system_parts: List[str],
    messages: List[Dict[str, Any]],
    max_tokens: int,
    supports_tools: bool,
    allow_tools: bool,
    tool_specs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    system_prompt = "\n\n".join(
        [part for part in [base_system_prompt, *system_parts] if str(part or "").strip()]
    ).strip()
    request: Dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "max_tokens": int(max_tokens),
    }
    if system_prompt:
        request["system"] = system_prompt
    if supports_tools and allow_tools and tool_specs:
        request["tools"] = list(tool_specs)
        request["tool_choice"] = {"type": "auto"}
    return request


__all__ = ["build_request"]
