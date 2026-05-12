from __future__ import annotations

from typing import Any


def provider_loader_kwargs(agent: Any) -> dict[str, Any]:
    getter = getattr(agent, "_provider_loader_kwargs", None)
    if callable(getter):
        try:
            payload = dict(getter() or {})
            return payload
        except Exception:
            return {}
    cwd = getattr(agent, "cwd", None)
    return {"cwd": cwd} if cwd is not None else {}


def load_catalog(runtime: Any) -> tuple[Any, dict[str, Any]]:
    agent = getattr(runtime, "agent", None)
    if agent is None:
        raise RuntimeError("provider agent unavailable")
    load_catalog_fn = getattr(agent, "_load_provider_catalog", None)
    if not callable(load_catalog_fn):
        raise RuntimeError("provider catalog loader unavailable")
    loader_kwargs = provider_loader_kwargs(agent)
    catalog = load_catalog_fn(**loader_kwargs)
    supplement = getattr(agent, "_supplement_provider_catalog", None)
    if callable(supplement):
        catalog = supplement(catalog)
    return catalog, loader_kwargs


def provider_aliases(
    runtime: Any,
    catalog: Any,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    alias_to_configs: dict[str, set[str]] = {}
    public_by_config: dict[str, str] = {}
    for config_name in sorted(getattr(catalog, "providers", {}).keys()):
        alias_to_configs.setdefault(config_name, set()).add(config_name)
        public_by_config.setdefault(config_name, config_name)
    try:
        provider_items = list(getattr(runtime.agent, "available_providers")() or [])
    except Exception:
        provider_items = []
    for item in provider_items:
        if not isinstance(item, dict):
            continue
        public_name = str(item.get("provider_name") or "").strip()
        config_name = str(item.get("config_provider_name") or public_name).strip()
        if not config_name:
            continue
        alias_to_configs.setdefault(config_name, set()).add(config_name)
        if public_name:
            alias_to_configs.setdefault(public_name, set()).add(config_name)
            public_by_config[config_name] = public_name
    return alias_to_configs, public_by_config


def resolve_provider_targets(
    runtime: Any,
    *,
    catalog: Any,
    provider_filter: str,
) -> tuple[list[str] | None, str | None, dict[str, str]]:
    alias_to_configs, public_by_config = provider_aliases(runtime, catalog)
    if not provider_filter:
        return sorted(getattr(catalog, "providers", {}).keys()), None, public_by_config
    resolved: set[str] = set()
    token = provider_filter.strip().lower()
    for alias, config_names in alias_to_configs.items():
        if alias.strip().lower() == token:
            resolved.update(config_names)
    if not resolved:
        return None, f"provider not found: {provider_filter}", public_by_config
    if len(resolved) > 1:
        joined = ", ".join(sorted(resolved))
        return None, f"provider is ambiguous: {provider_filter} ({joined})", public_by_config
    return sorted(resolved), None, public_by_config


def provider_display_name(public_by_config: dict[str, str], provider_name: str) -> str:
    return public_by_config.get(provider_name, provider_name)


__all__ = [
    "load_catalog",
    "provider_aliases",
    "provider_display_name",
    "provider_loader_kwargs",
    "resolve_provider_targets",
]
