"""Pure helper functions for provider options, details, and setup-command building.

Extracted from setup_modal so the UI widget stays separate from data plumbing.
"""

from __future__ import annotations

import shlex
from typing import Any


def default_setup_provider_options() -> list[str]:
    return ["openai", "anthropic"]


def normalized_setup_provider_options(values: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in list(values or []) + default_setup_provider_options():
        provider = str(value or "").strip()
        if not provider:
            continue
        key = provider.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(provider)
    return normalized or default_setup_provider_options()


def normalize_provider_details(values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for provider_name, raw_detail in dict(values or {}).items():
        provider = str(provider_name or "").strip()
        if not provider or not isinstance(raw_detail, dict):
            continue
        detail = dict(raw_detail)
        aliases = [provider, *list(detail.get("aliases") or [])]
        for alias in aliases:
            normalized_alias = str(alias or "").strip().lower()
            if normalized_alias:
                details[normalized_alias] = detail
    return details


def setup_provider_options_for_app(app: Any) -> list[str]:
    agent = getattr(getattr(app, "runtime", None), "agent", None)
    provider_status = getattr(agent, "provider_status", None)
    raw_values: list[str] = []
    if callable(provider_status):
        try:
            status = dict(provider_status() or {})
        except Exception:
            status = {}
        raw_values.extend(
            [
                str(status.get("provider_name") or ""),
                str(status.get("provider_public_name") or ""),
                str(status.get("effective_provider_name") or ""),
            ]
        )
    available_providers = getattr(agent, "available_providers", None)
    if callable(available_providers):
        try:
            items = list(available_providers() or [])
        except Exception:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_values.extend(
                [
                    str(item.get("provider_name") or ""),
                    str(item.get("display_name") or ""),
                    str(item.get("config_provider_name") or ""),
                ]
            )
    return normalized_setup_provider_options(raw_values)


def setup_provider_details_for_app(app: Any) -> dict[str, dict[str, Any]]:
    try:
        from cli.agent_cli import provider as provider_module
        from cli.agent_cli.providers.config.catalog import (
            candidate_api_key_names,
            default_model_entry,
            first_configured_key,
        )
    except Exception:
        return {}

    try:
        snapshot = provider_module.load_provider_management_snapshot(
            cwd=getattr(getattr(app, "runtime", None), "cwd", None)
        )
    except Exception:
        return {}

    catalog = getattr(snapshot, "catalog", None)
    auth_data = dict(getattr(snapshot, "auth_data", {}) or {})
    selected_config = getattr(snapshot, "selected_config", None)
    providers = dict(getattr(catalog, "providers", {}) or {})
    models = list(getattr(catalog, "models", {}).values() or [])
    details: dict[str, dict[str, Any]] = {}

    for provider_name, entry in providers.items():
        config_name = str(provider_name or "").strip()
        if not config_name:
            continue
        base_url = str(getattr(entry, "base_url", "") or "").strip()
        provider_models = _setup_model_names_for_provider(config_name, models)
        if not provider_models:
            default_entry = default_model_entry(config_name, catalog)
            default_model = str(getattr(default_entry, "model_id", "") or "").strip()
            if default_model:
                provider_models = [default_model]
        raw_provider = dict(getattr(entry, "raw_provider", {}) or {})
        default_model = (
            provider_models[0]
            if provider_models
            else str(getattr(entry, "default_model", "") or "").strip()
        )
        key_names = candidate_api_key_names(config_name, raw_provider, default_model, base_url)
        api_key_env = str(getattr(entry, "api_key_env", "") or "").strip()
        if api_key_env and api_key_env not in key_names:
            key_names.insert(0, api_key_env)
        api_key = first_configured_key(auth_data, key_names)
        if (
            selected_config is not None
            and str(getattr(selected_config, "provider_name", "") or "").strip().lower()
            == config_name.lower()
        ):
            api_key = api_key or str(getattr(selected_config, "api_key", "") or "").strip()
            base_url = base_url or str(getattr(selected_config, "base_url", "") or "").strip()
        aliases = [config_name, str(getattr(entry, "display_name", "") or "").strip()]
        details[config_name] = {
            "aliases": [alias for alias in aliases if alias],
            "base_url": base_url,
            "api_key": api_key,
            "models": provider_models,
        }
    return details


def _setup_model_names_for_provider(provider_name: str, models: list[Any]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for model in models:
        if str(getattr(model, "provider_name", "") or "").strip() != provider_name:
            continue
        name = (
            str(getattr(model, "display_name", "") or "").strip()
            or str(getattr(model, "model_id", "") or "").strip()
            or str(getattr(model, "key", "") or "").strip()
        )
        if not name or name in seen:
            continue
        seen.add(name)
        items.append(name)
    return items


def setup_command_from_payload(payload: dict[str, str]) -> str:
    command_parts = [
        "/setup",
        "provider",
        str(payload.get("provider") or "").strip(),
        "api-key",
        str(payload.get("api_key") or "").strip(),
        "user",
    ]
    base_url = str(payload.get("base_url") or "").strip()
    if base_url:
        command_parts.extend(["base-url", base_url])
    return " ".join(shlex.quote(part) for part in command_parts if str(part).strip())
