from __future__ import annotations

from typing import Any


def normalized(value: str) -> str:
    return str(value or "").strip().lower()


def optional_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def config_dict(config: Any, attr: str) -> dict[str, Any]:
    value = getattr(config, attr, None)
    if isinstance(value, dict):
        return dict(value)
    return {}


def config_bool_override(config: Any, keys: tuple[str, ...]) -> bool | None:
    for mapping in (config_dict(config, "raw_model"), config_dict(config, "raw_provider")):
        for key in keys:
            if key in mapping:
                return optional_bool(mapping.get(key), False)
    return None


def normalize_mode(value: Any, *, default: str = "live") -> str:
    token = str(value or "").strip().lower()
    return token if token in {"disabled", "cached", "live"} else default


def normalize_sandbox_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token if token in {"read-only", "workspace-write", "danger-full-access"} else ""


def mode_from_boolean(value: Any) -> str | None:
    if value is None:
        return None
    return "live" if optional_bool(value, False) else "cached"


def configured_mode(config: Any) -> tuple[str | None, str]:
    mode_keys = ("web_search_mode", "reference_web_search_mode")
    bool_keys = (
        "reference_web_search_external_web_access",
        "web_search_external_web_access",
        "external_web_access",
        "reference_web_search_live",
        "web_search_live",
    )
    for scope_name, mapping in (
        ("model", config_dict(config, "raw_model")),
        ("provider", config_dict(config, "raw_provider")),
    ):
        for key in mode_keys:
            if key in mapping:
                return normalize_mode(mapping.get(key)), f"{scope_name}.{key}"
        for key in bool_keys:
            if key in mapping:
                mode = mode_from_boolean(mapping.get(key))
                if mode is not None:
                    return mode, f"{scope_name}.{key}"
    return None, ""


def configured_sandbox_mode(config: Any) -> str:
    for mapping in (config_dict(config, "raw_model"), config_dict(config, "raw_provider")):
        if "sandbox_mode" not in mapping:
            continue
        normalized = normalize_sandbox_mode(mapping.get("sandbox_mode"))
        if normalized:
            return normalized
    return ""


def resolve_effective_mode_for_turn(
    *,
    requested_mode: str,
    default_mode: str,
    supported_modes: tuple[str, ...],
    sandbox_mode: str,
) -> tuple[str, str]:
    effective_mode = requested_mode if requested_mode in supported_modes else default_mode
    mode_resolution = "exact"
    if requested_mode != effective_mode:
        mode_resolution = "downgraded"
    if sandbox_mode == "danger-full-access" and effective_mode != "disabled":
        for candidate in ("live", "cached", "disabled"):
            if candidate not in supported_modes:
                continue
            if candidate != effective_mode:
                return candidate, "sandbox_promoted"
            break
    return effective_mode, mode_resolution


def config_identity(config: Any) -> tuple[str, str, str, str]:
    provider_name = normalized(getattr(config, "provider_name", ""))
    model = normalized(getattr(config, "model", "") or getattr(config, "model_key", ""))
    wire_api = normalized(getattr(config, "wire_api", ""))
    planner_kind = normalized(getattr(config, "planner_kind", ""))
    return provider_name, model, wire_api, planner_kind
