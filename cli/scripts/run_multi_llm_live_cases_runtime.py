from __future__ import annotations

from dataclasses import replace
from typing import Any


def _merged_route_config(
    route: Any,
    *,
    default_provider: str = "",
    default_model: str = "",
    default_reasoning_effort: str = "",
    default_timeout: int = 0,
    provider: str = "",
    model: str = "",
    reasoning_effort: str = "",
    timeout: int = 0,
) -> dict[str, Any]:
    merged = dict(route or {}) if isinstance(route, dict) else {}
    if not merged:
        if default_provider:
            merged["provider"] = str(default_provider).strip()
        if default_model:
            merged["model"] = str(default_model).strip()
        if default_reasoning_effort:
            merged["reasoning_effort"] = str(default_reasoning_effort).strip()
        if int(default_timeout or 0) > 0:
            merged["timeout"] = int(default_timeout)
    if provider:
        merged["provider"] = str(provider).strip()
    if model:
        merged["model"] = str(model).strip()
    if reasoning_effort:
        merged["reasoning_effort"] = str(reasoning_effort).strip()
    if int(timeout or 0) > 0:
        merged["timeout"] = int(timeout)
    return merged


def overlay_multi_llm_routes(
    config: Any,
    *,
    default_tool_followup_provider: str = "",
    default_tool_followup_model: str = "",
    default_tool_followup_reasoning_effort: str = "",
    default_tool_followup_timeout: int = 0,
    default_final_synthesis_provider: str = "",
    default_final_synthesis_model: str = "",
    default_final_synthesis_reasoning_effort: str = "",
    default_final_synthesis_timeout: int = 0,
    tool_followup_provider: str = "",
    tool_followup_model: str = "",
    tool_followup_reasoning_effort: str = "",
    tool_followup_timeout: int = 0,
    final_synthesis_provider: str = "",
    final_synthesis_model: str = "",
    final_synthesis_reasoning_effort: str = "",
    final_synthesis_timeout: int = 0,
) -> Any:
    if config is None:
        return config
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    routes = dict(raw_model.get("routes") or {}) if isinstance(raw_model.get("routes"), dict) else {}

    tool_followup = _merged_route_config(
        routes.get("tool_followup"),
        default_provider=default_tool_followup_provider,
        default_model=default_tool_followup_model,
        default_reasoning_effort=default_tool_followup_reasoning_effort,
        default_timeout=default_tool_followup_timeout,
        provider=tool_followup_provider,
        model=tool_followup_model,
        reasoning_effort=tool_followup_reasoning_effort,
        timeout=tool_followup_timeout,
    )
    if tool_followup:
        routes["tool_followup"] = tool_followup

    final_synthesis = _merged_route_config(
        routes.get("final_synthesis"),
        default_provider=default_final_synthesis_provider,
        default_model=default_final_synthesis_model,
        default_reasoning_effort=default_final_synthesis_reasoning_effort,
        default_timeout=default_final_synthesis_timeout,
        provider=final_synthesis_provider,
        model=final_synthesis_model,
        reasoning_effort=final_synthesis_reasoning_effort,
        timeout=final_synthesis_timeout,
    )
    if final_synthesis:
        routes["final_synthesis"] = final_synthesis

    raw_model["routes"] = routes
    return replace(config, raw_model=raw_model)
