from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.tools_core.tool_capability_resolver_config_runtime import (
    config_bool_override as _config_bool_override,
    config_identity as _config_identity,
    normalized as _normalized,
)


_MIXED_TOOLS_OVERRIDE_KEYS = (
    "native_web_search_mixed_tools",
    "native_web_search_tool_mix",
    "native_web_search_main_loop",
)


@dataclass(frozen=True, slots=True)
class NormalizedWebSearchResolverInput:
    provider_name: str = ""
    model: str = ""
    wire_api: str = ""
    planner_kind: str = ""


def native_web_search_resolver_input_kwargs(config: Any) -> dict[str, str]:
    provider_name, model, wire_api, planner_kind = _config_identity(config)
    return {
        "provider_name": provider_name,
        "model": model,
        "wire_api": wire_api,
        "planner_kind": planner_kind,
    }


def normalize_web_search_resolver_input(selection: Any) -> NormalizedWebSearchResolverInput:
    return NormalizedWebSearchResolverInput(
        provider_name=_normalized(getattr(selection, "provider_name", "")),
        model=_normalized(getattr(selection, "model", "")),
        wire_api=_normalized(getattr(selection, "wire_api", "")),
        planner_kind=_normalized(getattr(selection, "planner_kind", "")),
    )


def mixed_tools_override_enabled(config: Any) -> bool:
    override = _config_bool_override(config, _MIXED_TOOLS_OVERRIDE_KEYS)
    return bool(override) if override is not None else False


def native_web_search_override(config: Any) -> bool | None:
    return _config_bool_override(config, ("native_web_search",))


__all__ = [
    "NormalizedWebSearchResolverInput",
    "mixed_tools_override_enabled",
    "native_web_search_resolver_input_kwargs",
    "native_web_search_override",
    "normalize_web_search_resolver_input",
]
