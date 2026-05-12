from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.tools_core import browser_web_runtime, tool_registry_runtime, web_registry_runtime


def sync_browser_runtime_compat_bindings(
    *,
    load_browser_config: Any,
    resolve_browser_profiles: Any,
    create_browser_proxy_transport: Any,
) -> None:
    browser_web_runtime.load_browser_config = load_browser_config
    browser_web_runtime.resolve_browser_profiles = resolve_browser_profiles
    browser_web_runtime.create_browser_proxy_transport = create_browser_proxy_transport


def profile_prefers_local_browser(
    registry: Any,
    *,
    profile: str | None,
    load_browser_config: Any,
    resolve_browser_profiles: Any,
    create_browser_proxy_transport: Any,
) -> bool:
    sync_browser_runtime_compat_bindings(
        load_browser_config=load_browser_config,
        resolve_browser_profiles=resolve_browser_profiles,
        create_browser_proxy_transport=create_browser_proxy_transport,
    )
    return web_registry_runtime.profile_prefers_local_browser(registry, profile=profile)


def get_browser_executor(
    registry: Any,
    *,
    profile: str | None = None,
    transport: str | None = None,
    load_browser_config: Any,
    resolve_browser_profiles: Any,
    create_browser_proxy_transport: Any,
) -> Any | None:
    sync_browser_runtime_compat_bindings(
        load_browser_config=load_browser_config,
        resolve_browser_profiles=resolve_browser_profiles,
        create_browser_proxy_transport=create_browser_proxy_transport,
    )
    return web_registry_runtime.get_browser_executor(
        registry,
        profile=profile,
        transport=transport,
    )


def projected_mcp_tool_contracts(runtime: Any | None) -> List[Dict[str, Any]]:
    if runtime is None:
        return []
    projected_tool_contracts = getattr(runtime, "projected_tool_contracts", None)
    if not callable(projected_tool_contracts):
        return []
    try:
        raw = projected_tool_contracts()
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    rows = [dict(item) for item in raw if isinstance(item, dict)]
    rows.sort(key=lambda item: str(item.get("name") or ""))
    return rows


def capabilities_with_patchpoint(
    registry: Any,
    *,
    build_capabilities_payload_fn: Any,
) -> Dict[str, Any]:
    payload = tool_registry_runtime.capabilities(
        registry,
        build_capabilities_payload_fn=build_capabilities_payload_fn,
    )
    if not isinstance(payload, dict):
        return payload
    contracts = projected_mcp_tool_contracts(getattr(registry, "_mcp_runtime", None))
    if contracts:
        payload["mcp_tool_contracts"] = contracts
    return payload


def make_capabilities_method(
    *,
    build_capabilities_payload_getter: Callable[[], Any],
) -> Callable[[Any], Dict[str, Any]]:
    def capabilities(registry: Any) -> Dict[str, Any]:
        return capabilities_with_patchpoint(
            registry,
            build_capabilities_payload_fn=build_capabilities_payload_getter(),
        )

    return capabilities
