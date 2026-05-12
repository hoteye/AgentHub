from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.tools_core.tool_capability_resolver_config_runtime import (
    configured_mode as _configured_mode,
    configured_sandbox_mode as _configured_sandbox_mode,
    normalize_mode as _normalize_mode,
    resolve_effective_mode_for_turn as _resolve_effective_mode_for_turn,
)
from cli.agent_cli.tools_core.tool_backend_registry import backend_spec_by_id
from cli.agent_cli.tools_core.tool_capability_resolver_pure_helpers_runtime import (
    NativeWebSearchSupportState,
)


DEFAULT_MODES = ("disabled", "cached", "live")


@dataclass(frozen=True, slots=True)
class NativeWebSearchModeProjection:
    configurable_modes: tuple[str, ...] = DEFAULT_MODES
    supported_modes: tuple[str, ...] = DEFAULT_MODES
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


def project_native_web_search_mode(
    config: Any,
    *,
    selected_backend: str,
) -> NativeWebSearchModeProjection:
    backend_spec = backend_spec_by_id(selected_backend)
    configurable_modes = tuple(getattr(backend_spec, "configurable_modes", ()) or DEFAULT_MODES)
    supported_modes = tuple(getattr(backend_spec, "supported_modes", ()) or configurable_modes)
    default_mode = _normalize_mode(getattr(backend_spec, "default_mode", "live"), default="live")
    mode_binding = str(getattr(backend_spec, "mode_binding", "") or "").strip() or "canonical_best_effort"
    mode_support_level = str(getattr(backend_spec, "mode_support_level", "") or "").strip() or "explicit"
    cached_live_distinct = bool(getattr(backend_spec, "cached_live_distinct", True))
    mode_fallback_semantics = (
        str(getattr(backend_spec, "mode_fallback_semantics", "") or "").strip() or "none"
    )
    backend_notes = str(getattr(backend_spec, "notes", "") or "").strip()
    requested_mode, mode_source = _configured_mode(config)
    if not requested_mode:
        requested_mode = default_mode
        mode_source = "backend_default"
    effective_mode, mode_resolution = _resolve_effective_mode_for_turn(
        requested_mode=requested_mode,
        default_mode=default_mode,
        supported_modes=supported_modes,
        sandbox_mode=_configured_sandbox_mode(config),
    )
    if mode_source == "backend_default" and mode_resolution == "exact":
        mode_resolution = "backend_default"
    return NativeWebSearchModeProjection(
        configurable_modes=configurable_modes,
        supported_modes=supported_modes,
        default_mode=default_mode,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        mode_resolution=mode_resolution,
        mode_source=mode_source,
        mode_binding=mode_binding,
        mode_support_level=mode_support_level,
        cached_live_distinct=cached_live_distinct,
        mode_fallback_semantics=mode_fallback_semantics,
        backend_notes=backend_notes,
    )


def project_native_web_search_capability_kwargs(
    *,
    provider_family: str,
    selected_backend: str,
    mode_projection: NativeWebSearchModeProjection,
    support_state: NativeWebSearchSupportState,
    snapshot: Any,
) -> dict[str, Any]:
    return {
        "provider_family": provider_family,
        "selected_backend": selected_backend,
        "supports_runtime_native": support_state.supports_runtime_native,
        "supports_main_loop_native": support_state.main_loop_spec_kind != "function",
        "supports_mixed_tools_native": support_state.supports_mixed_tools_native,
        "main_loop_spec_kind": support_state.main_loop_spec_kind,
        "native_tool_type": support_state.native_tool_type,
        "configurable_modes": mode_projection.configurable_modes,
        "supported_modes": mode_projection.supported_modes,
        "default_mode": mode_projection.default_mode,
        "requested_mode": mode_projection.requested_mode,
        "effective_mode": mode_projection.effective_mode,
        "mode_resolution": mode_projection.mode_resolution,
        "mode_source": mode_projection.mode_source,
        "mode_binding": mode_projection.mode_binding,
        "mode_support_level": mode_projection.mode_support_level,
        "cached_live_distinct": mode_projection.cached_live_distinct,
        "mode_fallback_semantics": mode_projection.mode_fallback_semantics,
        "backend_notes": mode_projection.backend_notes,
        "availability": _snapshot_str(snapshot, "availability", default="unknown"),
        "confidence": _snapshot_str(snapshot, "confidence", default="low"),
        "decision_source": _snapshot_str(snapshot, "decision_source", default="fallback"),
        "reason": _snapshot_str(snapshot, "reason"),
        "checked_at": _snapshot_str(snapshot, "checked_at"),
        "cache_key": _snapshot_str(snapshot, "cache_key"),
        "cache_status": _snapshot_str(snapshot, "cache_status"),
        "cache_expires_at": _snapshot_str(snapshot, "cache_expires_at"),
        "cache_source": _snapshot_str(snapshot, "cache_source"),
    }


def _snapshot_str(snapshot: Any, attr: str, *, default: str = "") -> str:
    value = str(getattr(snapshot, attr, "") or "").strip()
    return value or default


__all__ = [
    "NativeWebSearchModeProjection",
    "project_native_web_search_capability_kwargs",
    "project_native_web_search_mode",
]
