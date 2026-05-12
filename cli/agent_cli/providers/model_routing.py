from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Mapping

from cli.agent_cli.providers.config_catalog import ProviderConfig

STANDARD_ROUTE_NAMES = (
    "policy_helper",
    "tool_followup",
    "final_synthesis",
)
STANDARD_DELEGATION_NAMES = (
    "subagent",
    "teammate",
)
_INHERIT_MODEL_TOKENS = {"default", "auto", "inherit"}


@dataclass(frozen=True)
class RouteResolution:
    route_name: str
    config: ProviderConfig | None
    timeout: int | None = None
    source: str = "missing"
    selector: str = ""
    configured: bool = False

    def public_summary(self) -> Dict[str, Any]:
        config = self.config
        return {
            "route_name": self.route_name,
            "configured": bool(self.configured),
            "source": str(self.source or "missing"),
            "selector": str(self.selector or ""),
            "timeout": self.timeout,
            "provider_name": str(config.provider_name or "") if config is not None else "",
            "model_key": str(config.model_key or "") if config is not None else "",
            "planner_kind": str(config.planner_kind or "") if config is not None else "",
            "wire_api": str(config.wire_api or "") if config is not None else "",
            "model": str(config.model or "") if config is not None else "",
            "base_url": str(config.base_url or "") if config is not None else "",
            "reasoning_effort": str(config.reasoning_effort or "") if config is not None else "",
        }


def _mapping_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _config_block(config: ProviderConfig, block_group: str, block_name: str) -> Dict[str, Any]:
    raw_model = _mapping_dict(config.raw_model)
    blocks = raw_model.get(block_group)
    if not isinstance(blocks, Mapping):
        return {}
    block_value = blocks.get(block_name)
    return _mapping_dict(block_value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _load_provider_config_for_route(
    *,
    cwd: str | None = None,
    env_overrides: Dict[str, str] | None = None,
) -> ProviderConfig | None:
    from cli.agent_cli.provider import load_provider_config

    return load_provider_config(
        cwd=cwd,
        env_overrides=env_overrides,
    )


def _selector_text(block: Mapping[str, Any]) -> str:
    return (
        str(block.get("model") or "").strip()
        or str(block.get("selector") or "").strip()
        or str(block.get("model_key") or "").strip()
    )


def _inherit_selector(selector: str) -> bool:
    return str(selector or "").strip().lower() in _INHERIT_MODEL_TOKENS


def _config_with_optional_reasoning(config: ProviderConfig, reasoning_effort: str) -> ProviderConfig:
    if not reasoning_effort:
        return config
    return replace(config, reasoning_effort=reasoning_effort)


def _resolve_config_for_role(
    config: ProviderConfig,
    role_name: str,
    *,
    block_group: str,
    default_source: str,
    fallback_main_source: str,
    allow_inherit: bool = False,
    cwd: str | None = None,
    fallback_to_main: bool = True,
    default_timeout: int | None = None,
    legacy_selector: str | None = None,
) -> RouteResolution:
    block = _config_block(config, block_group, role_name)
    block_source = str(block.get("source") or default_source).strip() or default_source
    block_timeout = _optional_int(block.get("timeout"))
    timeout = block_timeout if block_timeout is not None else _optional_int(default_timeout)
    selector = _selector_text(block)
    provider_name = str(block.get("provider") or "").strip()
    reasoning_effort = str(block.get("reasoning_effort") or "").strip()
    role_defined = bool(block)

    if role_defined:
        inherit_main = allow_inherit and ((not selector and not provider_name) or _inherit_selector(selector))
        if inherit_main:
            return RouteResolution(
                route_name=role_name,
                config=_config_with_optional_reasoning(config, reasoning_effort),
                timeout=timeout,
                source=f"{block_source}_{fallback_main_source}",
                selector=selector,
                configured=True,
            )
        if not selector and not provider_name and (reasoning_effort or timeout is not None):
            return RouteResolution(
                route_name=role_name,
                config=_config_with_optional_reasoning(config, reasoning_effort),
                timeout=timeout,
                source=block_source,
                selector="",
                configured=True,
            )
        env_overrides: Dict[str, str] = {}
        if provider_name:
            env_overrides["AGENT_CLI_PROVIDER"] = provider_name
        if selector:
            env_overrides["AGENT_CLI_MODEL"] = selector
        if reasoning_effort:
            env_overrides["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
        if env_overrides:
            resolved = _load_provider_config_for_route(cwd=cwd, env_overrides=env_overrides)
            if resolved is not None:
                return RouteResolution(
                    route_name=role_name,
                    config=resolved,
                    timeout=timeout,
                    source=block_source,
                    selector=selector or provider_name,
                    configured=True,
                )
        if fallback_to_main:
            fallback_config = _config_with_optional_reasoning(config, reasoning_effort)
            return RouteResolution(
                route_name=role_name,
                config=fallback_config,
                timeout=timeout,
                source=f"{block_source}_fallback_main",
                selector=selector or provider_name,
                configured=True,
            )
        return RouteResolution(
            route_name=role_name,
            config=None,
            timeout=timeout,
            source="missing",
            selector=selector or provider_name,
            configured=True,
        )

    legacy_token = str(legacy_selector or "").strip()
    if legacy_token:
        if allow_inherit and _inherit_selector(legacy_token):
            return RouteResolution(
                route_name=role_name,
                config=_config_with_optional_reasoning(config, ""),
                timeout=timeout,
                source=f"legacy_{fallback_main_source}",
                selector=legacy_token,
                configured=True,
            )
        resolved = _load_provider_config_for_route(
            cwd=cwd,
            env_overrides={"AGENT_CLI_MODEL": legacy_token},
        )
        if resolved is not None:
            return RouteResolution(
                route_name=role_name,
                config=resolved,
                timeout=timeout,
                source="legacy",
                selector=legacy_token,
                configured=True,
            )
        if fallback_to_main:
            return RouteResolution(
                route_name=role_name,
                config=config,
                timeout=timeout,
                source="legacy_fallback_main",
                selector=legacy_token,
                configured=True,
            )
        return RouteResolution(
            route_name=role_name,
            config=None,
            timeout=timeout,
            source="missing",
            selector=legacy_token,
            configured=True,
        )

    if fallback_to_main:
        return RouteResolution(
            route_name=role_name,
            config=config,
            timeout=timeout,
            source=fallback_main_source,
            selector="",
            configured=False,
        )
    return RouteResolution(
        route_name=role_name,
        config=None,
        timeout=timeout,
        source="missing",
        selector="",
        configured=False,
    )


def resolve_route_config(
    config: ProviderConfig,
    route_name: str,
    *,
    cwd: str | None = None,
    fallback_to_main: bool = True,
    default_timeout: int | None = None,
    legacy_selector: str | None = None,
) -> RouteResolution:
    return _resolve_config_for_role(
        config,
        route_name,
        block_group="routes",
        default_source="route",
        fallback_main_source="main",
        cwd=cwd,
        fallback_to_main=fallback_to_main,
        default_timeout=default_timeout,
        legacy_selector=legacy_selector,
    )


def resolve_delegation_config(
    config: ProviderConfig,
    role_name: str,
    *,
    cwd: str | None = None,
    fallback_to_main: bool = True,
    default_timeout: int | None = None,
) -> RouteResolution:
    return _resolve_config_for_role(
        config,
        role_name,
        block_group="delegation",
        default_source="delegation",
        fallback_main_source="inherit_main",
        allow_inherit=True,
        cwd=cwd,
        fallback_to_main=fallback_to_main,
        default_timeout=default_timeout,
    )
