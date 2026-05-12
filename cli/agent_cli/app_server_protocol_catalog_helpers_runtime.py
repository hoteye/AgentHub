from __future__ import annotations

from typing import Any

from cli.agent_cli import app_server_protocol_normalization_helpers_runtime as normalization_helpers


def available_model_items(
    agent: Any,
    *,
    provider_filter: str,
    include_hidden: bool,
) -> list[Any]:
    available_models = getattr(agent, "available_models", None)
    try:
        if callable(available_models):
            try:
                items = list(available_models(provider_filter or None, include_hidden=include_hidden) or [])
            except TypeError:
                try:
                    items = list(available_models(provider_filter or None) or [])
                except TypeError:
                    items = list(available_models() or [])
        else:
            items = []
    except Exception:
        items = []
    if include_hidden:
        return items
    return [item for item in items if not normalization_helpers.model_hidden(dict(item))]


def current_model_tokens(provider_status: dict[str, Any]) -> set[str]:
    tokens = {
        str(provider_status.get("provider_model") or "").strip(),
        str(provider_status.get("model_key") or "").strip(),
    }
    tokens.discard("")
    return tokens


def runtime_capabilities(runtime: Any) -> dict[str, Any]:
    tools = getattr(runtime, "tools", None)
    capabilities_getter = getattr(tools, "capabilities", None)
    if not callable(capabilities_getter):
        return {}
    try:
        return dict(capabilities_getter() or {})
    except Exception:
        return {}
