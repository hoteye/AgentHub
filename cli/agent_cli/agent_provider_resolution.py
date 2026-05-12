from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.provider import _project_claude_home_dir
from cli.agent_cli.providers.config.catalog import ModelCatalogEntry, ProviderCatalog, ProviderCatalogEntry
from cli.agent_cli.providers.protocols.anthropic_messages import load_claude_provider_config
from cli.agent_cli.providers.registry import infer_vendor


def public_provider_name(
    *,
    provider_name: str,
    model: str = "",
    base_url: str = "",
    planner_kind: str = "",
) -> str:
    raw_name = str(provider_name or "").strip()
    inferred = infer_vendor(
        provider_name=raw_name,
        model=str(model or "").strip(),
        base_url=str(base_url or "").strip(),
        planner_kind="",
    )
    if inferred is not None:
        return inferred.name
    if raw_name:
        return raw_name
    inferred = infer_vendor(
        provider_name=raw_name,
        model=str(model or "").strip(),
        base_url=str(base_url or "").strip(),
        planner_kind=str(planner_kind or "").strip(),
    )
    return inferred.name if inferred is not None else raw_name


def resolution_status_label(summary: Dict[str, Any]) -> str:
    source = str(summary.get("effective_source") or summary.get("source") or "missing").strip() or "missing"
    provider_name = str(summary.get("effective_provider_name") or summary.get("provider_name") or "-").strip() or "-"
    model = str(summary.get("effective_model") or summary.get("model") or "-").strip() or "-"
    reasoning_effort = str(summary.get("reasoning_effort") or "").strip()
    timeout = summary.get("timeout")
    parts = [provider_name, model]
    if reasoning_effort:
        parts.append(f"reasoning={reasoning_effort}")
    if timeout not in (None, ""):
        parts.append(f"timeout={timeout}")
    if bool(summary.get("availability_fallback_to_main")):
        parts.append("availability_fallback=true")
    parts.append(f"source={source}")
    return " | ".join(parts)


def supplement_catalog_with_project_local_providers(catalog: ProviderCatalog) -> ProviderCatalog:
    return supplement_catalog_with_project_local_providers_with_overrides(
        catalog,
        project_claude_home_dir_fn=_project_claude_home_dir,
        load_claude_provider_config_fn=load_claude_provider_config,
    )


def supplement_catalog_with_project_local_providers_with_overrides(
    catalog: ProviderCatalog,
    *,
    project_claude_home_dir_fn: Any,
    load_claude_provider_config_fn: Any,
) -> ProviderCatalog:
    claude_home = project_claude_home_dir_fn()
    if claude_home is None:
        return catalog
    claude_config = load_claude_provider_config_fn(env_mapping={}, home_dir=claude_home)
    if claude_config is None:
        return catalog

    provider_name = str(claude_config.provider_name or "anthropic").strip() or "anthropic"
    model_key = str(claude_config.model_key or claude_config.model or "claude-sonnet-4-6").strip()
    model_id = str(claude_config.model or model_key).strip() or model_key

    provider_entry = catalog.providers.get(provider_name)
    if provider_entry is None:
        catalog.providers[provider_name] = ProviderCatalogEntry(
            provider_name=provider_name,
            display_name=provider_name,
            base_url=str(claude_config.base_url or "").strip() or None,
            api_key_env="ANTHROPIC_API_KEY",
            planner_kind=str(claude_config.planner_kind or "").strip(),
            wire_api=str(claude_config.wire_api or "").strip(),
            default_model=model_key,
            raw_provider=dict(claude_config.raw_provider or {}),
        )
    elif not provider_entry.default_model:
        provider_entry.default_model = model_key

    if model_key not in catalog.models:
        catalog.models[model_key] = ModelCatalogEntry(
            key=model_key,
            provider_name=provider_name,
            model_id=model_id,
            display_name=model_id,
            planner_kind=str(claude_config.planner_kind or "").strip(),
            wire_api=str(claude_config.wire_api or "").strip(),
            supports_tools=True,
            supports_reasoning=False,
            raw_model=dict(claude_config.raw_model or {}),
        )
    return catalog
