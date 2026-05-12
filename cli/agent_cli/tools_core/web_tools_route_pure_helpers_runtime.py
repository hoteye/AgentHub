from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.tools_core import web_tools_route_payload_runtime
from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
    backend_spec_by_id,
)
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    default_web_search_probe_cache_lookup,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_route_normalization_helpers_runtime import (
    normalized_supported_modes,
    probe_cache_lookup_from_config,
    provider_config_value,
)


_PROBE_BYPASS_DECISION_SOURCES = frozenset(
    {
        "static_rule",
        "explicit_profile",
        "catalog_default",
        "provider_endpoint",
    }
)


def resolve_web_search_route(
    *,
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
) -> tuple[dict[str, Any], Any | None]:
    config = provider_config_value(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
    )
    resolver_input = WebSearchResolverInput(
        provider_name=str(getattr(config, "provider_name", "") or "").strip(),
        model=str(getattr(config, "model", "") or "").strip(),
        wire_api=str(getattr(config, "wire_api", "") or "").strip(),
        planner_kind=str(getattr(config, "planner_kind", "") or "").strip(),
    )
    resolved_probe_cache_lookup = (
        probe_cache_lookup
        or probe_cache_lookup_from_config(config)
        or default_web_search_probe_cache_lookup
    )
    if not callable(resolved_probe_cache_lookup):
        resolved_probe_cache_lookup = default_web_search_probe_cache_lookup
    probe_lookup_calls = 0
    resolver_supports_probe_lookup = True

    def _tracked_probe_cache_lookup(cache_key: Any) -> Any:
        nonlocal probe_lookup_calls
        probe_lookup_calls += 1
        return resolved_probe_cache_lookup(cache_key)

    try:
        snapshot = resolve_web_search_capability_fn(
            resolver_input,
            probe_cache_lookup=_tracked_probe_cache_lookup,
        )
    except TypeError:
        resolver_supports_probe_lookup = False
        snapshot = resolve_web_search_capability_fn(resolver_input)
    selected_backend_id = str(getattr(snapshot, "selected_backend", "") or "").strip() or BACKEND_LOCAL_WEB_SEARCH
    selected_spec = backend_spec_by_id_fn(selected_backend_id)
    runtime_native_capability = resolve_native_web_search_capability(config) if config is not None else None
    decision_source = str(getattr(snapshot, "decision_source", "") or "").strip()
    cache_key = str(getattr(snapshot, "cache_key", "") or "").strip()
    cache_status = str(getattr(snapshot, "cache_status", "") or "").strip()
    cache_expires_at = str(getattr(snapshot, "cache_expires_at", "") or "").strip()
    cache_source = str(getattr(snapshot, "cache_source", "") or "").strip()
    probe_bypass = probe_lookup_calls <= 0
    probe_bypass_reason = ""
    if probe_bypass:
        if not resolver_supports_probe_lookup:
            probe_bypass_reason = "resolver_probe_lookup_unobservable"
        elif decision_source in _PROBE_BYPASS_DECISION_SOURCES:
            probe_bypass_reason = f"{decision_source}_hit"
        else:
            probe_bypass_reason = "probe_lookup_not_invoked"
    supported_modes = normalized_supported_modes(
        getattr(snapshot, "supported_modes", None)
        or getattr(runtime_native_capability, "supported_modes", None)
        or getattr(selected_spec, "supported_modes", None)
    )
    return (
        {
            "tool": "web_search",
            "selected_backend_id": selected_backend_id,
            "selected_backend_kind": str(getattr(selected_spec, "backend_kind", "") or "").strip() or "unknown",
            "availability": str(getattr(snapshot, "availability", "") or "").strip(),
            "confidence": str(getattr(snapshot, "confidence", "") or "").strip(),
            "decision_source": decision_source,
            "reason": str(getattr(snapshot, "reason", "") or "").strip(),
            "checked_at": str(getattr(snapshot, "checked_at", "") or "").strip(),
            "cache_hit": decision_source == "probe_cache",
            "cache_key": cache_key,
            "cache_status": cache_status,
            "cache_expires_at": cache_expires_at,
            "cache_source": cache_source,
            "probe_bypass": probe_bypass,
            "probe_bypass_reason": probe_bypass_reason,
            "probe_lookup_calls": probe_lookup_calls,
            "provider_name": resolver_input.provider_name,
            "model": resolver_input.model,
            "planner_kind": resolver_input.planner_kind,
            "wire_api": resolver_input.wire_api,
            "supported_modes": supported_modes,
            "default_mode": str(
                getattr(snapshot, "default_mode", "")
                or getattr(runtime_native_capability, "default_mode", "")
                or getattr(selected_spec, "default_mode", "")
                or ""
            ).strip(),
            "requested_mode": str(
                getattr(snapshot, "requested_mode", "") or getattr(runtime_native_capability, "requested_mode", "") or ""
            ).strip(),
            "effective_mode": str(
                getattr(snapshot, "effective_mode", "") or getattr(runtime_native_capability, "effective_mode", "") or ""
            ).strip(),
            "mode_source": str(
                getattr(snapshot, "mode_source", "") or getattr(runtime_native_capability, "mode_source", "") or ""
            ).strip(),
            "mode_binding": str(
                getattr(snapshot, "mode_binding", "")
                or getattr(runtime_native_capability, "mode_binding", "")
                or getattr(selected_spec, "mode_binding", "")
                or ""
            ).strip(),
        },
        config,
    )


def resolve_native_web_search_capability(config: Any) -> Any:
    return web_tools_route_payload_runtime.resolve_native_web_search_capability(config)


def effective_web_search_backend(
    route: dict[str, Any],
    *,
    provider_config: Any | None,
    resolve_native_web_search_capability_fn: Callable[[Any], Any],
) -> tuple[str, str, str]:
    selected_backend_id = str(route.get("selected_backend_id") or "").strip()
    capability = None
    if provider_config is not None:
        capability = resolve_native_web_search_capability_fn(provider_config)
    if (
        selected_backend_id == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
        and capability is not None
        and bool(getattr(capability, "supports_runtime_native", False))
    ):
        return (BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH, "openai_responses_native", "")
    if (
        selected_backend_id == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
        and capability is not None
        and bool(getattr(capability, "supports_runtime_native", False))
    ):
        return (BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH, "anthropic_native", "")
    fallback_reason = ""
    if selected_backend_id == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH:
        fallback_reason = "openai_responses_native_not_available"
    elif selected_backend_id == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH:
        fallback_reason = "anthropic_native_not_available"
    elif selected_backend_id and selected_backend_id != BACKEND_LOCAL_WEB_SEARCH:
        fallback_reason = "requested_backend_not_available_in_runtime"
    return (BACKEND_LOCAL_WEB_SEARCH, "local_fallback", fallback_reason)


def runtime_web_search_route(
    *,
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[[Any], Any] = resolve_native_web_search_capability,
) -> dict[str, Any]:
    route, resolved_config = resolve_web_search_route(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
    )
    effective_backend_id, execution_path, fallback_reason = effective_web_search_backend(
        route,
        provider_config=resolved_config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )
    effective_spec = backend_spec_by_id_fn(effective_backend_id)
    return {
        **route,
        "effective_backend_id": effective_backend_id,
        "effective_backend_kind": str(getattr(effective_spec, "backend_kind", "") or "").strip() or "unknown",
        "execution_path": execution_path,
        "fallback_reason": fallback_reason,
    }


__all__ = [
    "effective_web_search_backend",
    "resolve_native_web_search_capability",
    "resolve_web_search_route",
    "runtime_web_search_route",
]
