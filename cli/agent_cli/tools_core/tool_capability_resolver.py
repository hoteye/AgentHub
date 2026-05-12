from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
)
from cli.agent_cli.tools_core.tool_capabilities import (
    ToolCapabilitySnapshot,
    WebSearchProbeCacheKey,
)
from cli.agent_cli.tools_core.tool_capability_resolver_normalization_helpers_runtime import (
    mixed_tools_override_enabled as _mixed_tools_override,
    native_web_search_resolver_input_kwargs as _native_web_search_resolver_input_kwargs,
    native_web_search_override as _native_web_search_override,
    normalize_web_search_resolver_input,
)
from cli.agent_cli.tools_core.tool_capability_resolver_projection_helpers_runtime import (
    project_native_web_search_capability_kwargs,
    project_native_web_search_mode,
)
from cli.agent_cli.tools_core.tool_capability_resolver_pure_helpers_runtime import (
    resolve_fallback_web_search_capability,
    resolve_native_web_search_defaults,
    resolve_native_web_search_support_state,
    resolve_provider_family,
    resolve_static_web_search_capability,
)
from cli.agent_cli.tools_core.web_search_probe_cache_runtime import (
    default_web_search_probe_cache_lookup as runtime_default_web_search_probe_cache_lookup,
    probe_cache_web_search_snapshot,
)


@dataclass(frozen=True, slots=True)
class WebSearchResolverInput:
    provider_name: str = ""
    model: str = ""
    wire_api: str = ""
    planner_kind: str = ""


@dataclass(frozen=True, slots=True)
class NativeWebSearchCapability:
    provider_family: str = ""
    selected_backend: str = BACKEND_LOCAL_WEB_SEARCH
    supports_runtime_native: bool = False
    supports_main_loop_native: bool = False
    supports_mixed_tools_native: bool = False
    main_loop_spec_kind: str = "function"
    native_tool_type: str = ""
    configurable_modes: tuple[str, ...] = ("disabled", "cached", "live")
    supported_modes: tuple[str, ...] = ("disabled", "cached", "live")
    default_mode: str = "live"
    requested_mode: str = "live"
    effective_mode: str = "live"
    mode_resolution: str = "backend_default"
    mode_source: str = "backend_default"
    mode_binding: str = "canonical_best_effort"
    mode_support_level: str = "explicit"
    cached_live_distinct: bool = True
    mode_fallback_semantics: str = "none"
    backend_notes: str = ""
    availability: str = "unknown"
    confidence: str = "low"
    decision_source: str = "fallback"
    reason: str = ""
    checked_at: str = ""
    cache_key: str = ""
    cache_status: str = ""
    cache_expires_at: str = ""
    cache_source: str = ""


def _native_web_search_resolver_input(config: Any) -> WebSearchResolverInput:
    return WebSearchResolverInput(**_native_web_search_resolver_input_kwargs(config))


def resolve_native_web_search_capability(
    config: Any,
    *,
    resolve_web_search_capability_fn: Callable[..., ToolCapabilitySnapshot] | None = None,
    probe_cache_lookup: Callable[[WebSearchProbeCacheKey], Any] | None = None,
) -> NativeWebSearchCapability:
    selection = _native_web_search_resolver_input(config)
    normalized_selection = normalize_web_search_resolver_input(selection)
    resolve_fn = resolve_web_search_capability_fn or resolve_web_search_capability
    try:
        snapshot = resolve_fn(
            selection,
            probe_cache_lookup=probe_cache_lookup,
        )
    except TypeError:
        snapshot = resolve_fn(selection)

    native_override = _native_web_search_override(config)
    mixed_tools_opt_in = _mixed_tools_override(config)

    selected_backend = str(getattr(snapshot, "selected_backend", "") or "").strip() or BACKEND_LOCAL_WEB_SEARCH
    mode_projection = project_native_web_search_mode(
        config,
        selected_backend=selected_backend,
    )
    defaults = resolve_native_web_search_defaults(
        selection=normalized_selection,
        selected_backend=selected_backend,
    )
    support_state = resolve_native_web_search_support_state(
        selected_backend=selected_backend,
        native_override=native_override,
        mixed_tools_opt_in=mixed_tools_opt_in,
        effective_mode=mode_projection.effective_mode,
        defaults=defaults,
    )
    provider_family = resolve_provider_family(
        selection=normalized_selection,
        selected_backend=selected_backend,
        defaults=defaults,
    )

    return NativeWebSearchCapability(
        **project_native_web_search_capability_kwargs(
            provider_family=provider_family,
            selected_backend=selected_backend,
            mode_projection=mode_projection,
            support_state=support_state,
            snapshot=snapshot,
        )
    )


def default_web_search_probe_cache_lookup(cache_key: WebSearchProbeCacheKey) -> Any:
    return runtime_default_web_search_probe_cache_lookup(cache_key)


def _probe_cache_snapshot(
    *,
    provider_name: str,
    model: str,
    wire_api: str,
    planner_kind: str,
    probe_cache_lookup: Callable[[WebSearchProbeCacheKey], Any] | None,
) -> ToolCapabilitySnapshot | None:
    return probe_cache_web_search_snapshot(
        provider_name=provider_name,
        model=model,
        wire_api=wire_api,
        planner_kind=planner_kind,
        probe_cache_lookup=probe_cache_lookup,
    )


def resolve_web_search_capability(
    selection: WebSearchResolverInput,
    *,
    probe_cache_lookup: Callable[[WebSearchProbeCacheKey], Any] | None = None,
) -> ToolCapabilitySnapshot:
    normalized_selection = normalize_web_search_resolver_input(selection)
    resolved_probe_cache_lookup = probe_cache_lookup or default_web_search_probe_cache_lookup

    static_snapshot = resolve_static_web_search_capability(normalized_selection)
    if static_snapshot is not None:
        return static_snapshot

    cached = _probe_cache_snapshot(
        provider_name=normalized_selection.provider_name,
        model=normalized_selection.model,
        wire_api=normalized_selection.wire_api,
        planner_kind=normalized_selection.planner_kind,
        probe_cache_lookup=resolved_probe_cache_lookup,
    )
    if cached is not None:
        return cached

    return resolve_fallback_web_search_capability(normalized_selection)
