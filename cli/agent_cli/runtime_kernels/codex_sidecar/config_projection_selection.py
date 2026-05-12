from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.providers.config.catalog import ModelCatalogEntry, ProviderCatalog


def _selected_provider_name(
    *,
    catalog: ProviderCatalog,
    toml_data: Mapping[str, Any],
) -> str:
    configured_provider = str(toml_data.get("model_provider") or "").strip()
    if configured_provider and configured_provider in catalog.providers:
        return configured_provider
    configured_model = str(toml_data.get("model") or "").strip()
    model_entry = _find_model(catalog, configured_model, preferred_provider=configured_provider)
    if model_entry is not None:
        return model_entry.provider_name
    if configured_provider:
        return configured_provider
    return next(iter(catalog.providers), "")


def _selected_model_entry(
    *,
    catalog: ProviderCatalog,
    provider_name: str,
    toml_data: Mapping[str, Any],
) -> ModelCatalogEntry | None:
    configured_model = str(toml_data.get("model") or "").strip()
    entry = _find_model(catalog, configured_model, preferred_provider=provider_name)
    if entry is not None:
        return entry
    provider = catalog.providers.get(provider_name)
    default_model = str(getattr(provider, "default_model", "") or "").strip()
    return _find_model(catalog, default_model, preferred_provider=provider_name)


def _find_model(
    catalog: ProviderCatalog,
    selector: str,
    *,
    preferred_provider: str = "",
) -> ModelCatalogEntry | None:
    normalized = str(selector or "").strip()
    if not normalized:
        return None
    provider = str(preferred_provider or "").strip()
    for entry in catalog.models.values():
        if provider and entry.provider_name != provider:
            continue
        if normalized in {entry.key, entry.model_id}:
            return entry
    for entry in catalog.models.values():
        if normalized in {entry.key, entry.model_id}:
            return entry
    return None
