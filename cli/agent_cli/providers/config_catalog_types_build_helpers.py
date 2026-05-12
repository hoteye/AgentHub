from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from cli.agent_cli.providers.config_catalog_types_pure_helpers import aliased_mapping_value, slugify_model_key


def build_provider_catalog(
    toml_data: Dict[str, Any],
    *,
    provider_catalog_factory: Callable[[], Any],
    provider_catalog_entry_factory: Callable[..., Any],
    model_catalog_entry_factory: Callable[..., Any],
    apply_typed_auth_to_provider_block_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    provider_auth_schema_fn: Callable[[Mapping[str, Any]], Any],
    resolve_configured_interaction_profile_fn: Callable[..., tuple[str, str]],
    normalize_interaction_profile_fn: Callable[[Any], str],
    resolve_model_migration_fn: Callable[[str, Mapping[str, Any]], str],
    default_supports_reasoning_for_model_fn: Callable[..., bool],
    supported_reasoning_efforts_for_model_fn: Callable[..., tuple[str, ...]],
    default_reasoning_effort_for_model_fn: Callable[..., str],
    find_model_entry_fn: Callable[..., Any],
    optional_bool_fn: Callable[[Any, bool], bool],
    infer_planner_kind_fn: Callable[[str, str, Optional[str], Dict[str, Any]], str],
) -> Any:
    catalog = provider_catalog_factory()
    provider_blocks = (toml_data.get("model_providers") or {}) if isinstance(toml_data.get("model_providers"), dict) else {}
    model_blocks = (toml_data.get("models") or {}) if isinstance(toml_data.get("models"), dict) else {}
    configured_provider_name = str(toml_data.get("model_provider") or "").strip()
    configured_model_selector = resolve_model_migration_fn(str(toml_data.get("model") or "").strip(), toml_data)

    _populate_provider_entries(
        catalog,
        provider_blocks=provider_blocks,
        provider_catalog_entry_factory=provider_catalog_entry_factory,
        apply_typed_auth_to_provider_block_fn=apply_typed_auth_to_provider_block_fn,
        provider_auth_schema_fn=provider_auth_schema_fn,
        resolve_configured_interaction_profile_fn=resolve_configured_interaction_profile_fn,
        normalize_interaction_profile_fn=normalize_interaction_profile_fn,
    )
    _populate_model_entries(
        catalog,
        model_blocks=model_blocks,
        model_catalog_entry_factory=model_catalog_entry_factory,
        resolve_configured_interaction_profile_fn=resolve_configured_interaction_profile_fn,
        normalize_interaction_profile_fn=normalize_interaction_profile_fn,
        default_supports_reasoning_for_model_fn=default_supports_reasoning_for_model_fn,
        supported_reasoning_efforts_for_model_fn=supported_reasoning_efforts_for_model_fn,
        default_reasoning_effort_for_model_fn=default_reasoning_effort_for_model_fn,
        optional_bool_fn=optional_bool_fn,
    )
    _project_configured_default_model(
        catalog,
        configured_provider_name=configured_provider_name,
        configured_model_selector=configured_model_selector,
        find_model_entry_fn=find_model_entry_fn,
    )
    _synthesize_missing_default_models(
        catalog,
        model_catalog_entry_factory=model_catalog_entry_factory,
        find_model_entry_fn=find_model_entry_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
        default_supports_reasoning_for_model_fn=default_supports_reasoning_for_model_fn,
        supported_reasoning_efforts_for_model_fn=supported_reasoning_efforts_for_model_fn,
        default_reasoning_effort_for_model_fn=default_reasoning_effort_for_model_fn,
    )
    return catalog


def _populate_provider_entries(
    catalog: Any,
    *,
    provider_blocks: Dict[str, Any],
    provider_catalog_entry_factory: Callable[..., Any],
    apply_typed_auth_to_provider_block_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    provider_auth_schema_fn: Callable[[Mapping[str, Any]], Any],
    resolve_configured_interaction_profile_fn: Callable[..., tuple[str, str]],
    normalize_interaction_profile_fn: Callable[[Any], str],
) -> None:
    for provider_name, raw_provider in provider_blocks.items():
        if not isinstance(raw_provider, dict):
            continue
        provider_name = str(provider_name).strip()
        if not provider_name:
            continue
        projected_provider = apply_typed_auth_to_provider_block_fn(raw_provider)
        auth_schema = provider_auth_schema_fn(projected_provider)
        projected_auth = dict(auth_schema.auth)
        raw_auth = raw_provider.get("auth") if isinstance(raw_provider.get("auth"), Mapping) else {}
        if auth_schema.auth_mode in {"oauth", "wellknown"}:
            for key in ("token_ref", "session", "session_ref", "session_id"):
                extra = str(raw_auth.get(key) or raw_provider.get(key) or "").strip()
                if extra:
                    projected_auth[key] = extra
        default_model = str(projected_provider.get("default_model") or projected_provider.get("model") or "").strip()
        api_key_env = (
            str(projected_auth.get("env_var") or "").strip()
            or str(projected_provider.get("api_key_env") or projected_provider.get("auth_key_name") or "").strip()
        )
        catalog.providers[provider_name] = provider_catalog_entry_factory(
            provider_name=provider_name,
            display_name=str(projected_provider.get("name") or provider_name),
            base_url=str(projected_provider.get("base_url") or "").strip() or None,
            api_key_env=api_key_env,
            auth_mode=auth_schema.auth_mode,
            auth=projected_auth,
            planner_kind=str(projected_provider.get("planner") or projected_provider.get("planner_kind") or "").strip().lower(),
            wire_api=str(projected_provider.get("wire_api") or "").strip().lower(),
            interaction_profile=resolve_configured_interaction_profile_fn(
                raw_model=None,
                raw_provider=projected_provider,
            )[0]
            or normalize_interaction_profile_fn(projected_provider.get("interaction_profile")),
            default_model=default_model,
            raw_provider=dict(projected_provider),
        )


def _populate_model_entries(
    catalog: Any,
    *,
    model_blocks: Dict[str, Any],
    model_catalog_entry_factory: Callable[..., Any],
    resolve_configured_interaction_profile_fn: Callable[..., tuple[str, str]],
    normalize_interaction_profile_fn: Callable[[Any], str],
    default_supports_reasoning_for_model_fn: Callable[..., bool],
    supported_reasoning_efforts_for_model_fn: Callable[..., tuple[str, ...]],
    default_reasoning_effort_for_model_fn: Callable[..., str],
    optional_bool_fn: Callable[[Any, bool], bool],
) -> None:
    for model_key, raw_model in model_blocks.items():
        if not isinstance(raw_model, dict):
            continue
        key = str(model_key).strip()
        provider_name = str(raw_model.get("provider") or "").strip()
        model_id = str(raw_model.get("model_id") or raw_model.get("model") or key).strip()
        if not key or not provider_name or not model_id:
            continue
        provider_entry = catalog.providers.get(provider_name)
        planner_kind = str(raw_model.get("planner") or raw_model.get("planner_kind") or "").strip().lower()
        wire_api = str(raw_model.get("wire_api") or (provider_entry.wire_api if provider_entry else "") or "").strip().lower()
        interaction_profile = (
            resolve_configured_interaction_profile_fn(
                raw_model=raw_model,
                raw_provider=None,
            )[0]
            or normalize_interaction_profile_fn(raw_model.get("interaction_profile"))
        )
        resolved_supports_reasoning = default_supports_reasoning_for_model_fn(
            provider_name=provider_name,
            model_id=model_id,
            supports_reasoning=raw_model.get("supports_reasoning"),
            reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
            reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
            supported_reasoning_efforts=aliased_mapping_value(
                raw_model, "supported_reasoning_efforts", "supportedReasoningEfforts"
            ),
            default_reasoning_effort=aliased_mapping_value(
                raw_model, "default_reasoning_effort", "defaultReasoningEffort"
            ),
        )
        resolved_supported_reasoning_efforts = supported_reasoning_efforts_for_model_fn(
            provider_name=provider_name,
            model_id=model_id,
            supports_reasoning=raw_model.get("supports_reasoning"),
            reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
            reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
            supported_reasoning_efforts=aliased_mapping_value(
                raw_model, "supported_reasoning_efforts", "supportedReasoningEfforts"
            ),
            default_reasoning_effort=aliased_mapping_value(
                raw_model, "default_reasoning_effort", "defaultReasoningEffort"
            ),
        )
        resolved_default_reasoning_effort = default_reasoning_effort_for_model_fn(
            provider_name=provider_name,
            model_id=model_id,
            interaction_profile=interaction_profile,
            planner_kind=planner_kind,
            wire_api=wire_api,
            supports_reasoning=raw_model.get("supports_reasoning"),
            reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
            reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
            supported_reasoning_efforts=resolved_supported_reasoning_efforts,
            default_reasoning_effort=aliased_mapping_value(
                raw_model, "default_reasoning_effort", "defaultReasoningEffort"
            ),
        )
        catalog.models[key] = model_catalog_entry_factory(
            key=key,
            provider_name=provider_name,
            model_id=model_id,
            display_name=str(raw_model.get("display_name") or model_id),
            planner_kind=planner_kind,
            wire_api=wire_api,
            interaction_profile=interaction_profile,
            supports_tools=optional_bool_fn(raw_model.get("supports_tools"), True),
            supports_reasoning=resolved_supports_reasoning,
            supported_reasoning_efforts=resolved_supported_reasoning_efforts,
            default_reasoning_effort=resolved_default_reasoning_effort,
            reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
            reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
            raw_model=dict(raw_model),
        )


def _project_configured_default_model(
    catalog: Any,
    *,
    configured_provider_name: str,
    configured_model_selector: str,
    find_model_entry_fn: Callable[..., Any],
) -> None:
    if configured_provider_name and configured_model_selector:
        configured_provider = catalog.providers.get(configured_provider_name)
        configured_model = find_model_entry_fn(
            configured_model_selector,
            catalog,
            preferred_provider=configured_provider_name,
        )
        if configured_provider is not None and not configured_provider.default_model:
            configured_provider.default_model = (
                configured_model.key if configured_model is not None else configured_model_selector
            )


def _synthesize_missing_default_models(
    catalog: Any,
    *,
    model_catalog_entry_factory: Callable[..., Any],
    find_model_entry_fn: Callable[..., Any],
    infer_planner_kind_fn: Callable[[str, str, Optional[str], Dict[str, Any]], str],
    default_supports_reasoning_for_model_fn: Callable[..., bool],
    supported_reasoning_efforts_for_model_fn: Callable[..., tuple[str, ...]],
    default_reasoning_effort_for_model_fn: Callable[..., str],
) -> None:
    for provider_name, provider_entry in list(catalog.providers.items()):
        selector = provider_entry.default_model
        if not selector:
            continue
        existing = find_model_entry_fn(selector, catalog, preferred_provider=provider_name)
        if existing is not None:
            continue
        key = slugify_model_key(selector)
        unique_key = key
        suffix = 2
        while unique_key in catalog.models:
            unique_key = f"{key}_{suffix}"
            suffix += 1
        planner_kind = infer_planner_kind_fn(provider_name, selector, provider_entry.base_url, provider_entry.raw_provider)
        resolved_supports_reasoning = default_supports_reasoning_for_model_fn(
            provider_name=provider_name,
            model_id=selector,
            supports_reasoning=None,
            reasoning_mode="reasoning_content" if "reasoner" in selector.lower() else "",
            reasoning_output_field="reasoning_content" if "reasoner" in selector.lower() else "",
        )
        resolved_supported_reasoning_efforts = supported_reasoning_efforts_for_model_fn(
            provider_name=provider_name,
            model_id=selector,
            supports_reasoning=resolved_supports_reasoning,
            reasoning_mode="reasoning_content" if "reasoner" in selector.lower() else "",
            reasoning_output_field="reasoning_content" if "reasoner" in selector.lower() else "",
        )
        resolved_default_reasoning_effort = default_reasoning_effort_for_model_fn(
            provider_name=provider_name,
            model_id=selector,
            interaction_profile=provider_entry.interaction_profile,
            planner_kind=planner_kind,
            wire_api=provider_entry.wire_api,
            supports_reasoning=resolved_supports_reasoning,
            reasoning_mode="reasoning_content" if "reasoner" in selector.lower() else "",
            reasoning_output_field="reasoning_content" if "reasoner" in selector.lower() else "",
            supported_reasoning_efforts=resolved_supported_reasoning_efforts,
        )
        catalog.models[unique_key] = model_catalog_entry_factory(
            key=unique_key,
            provider_name=provider_name,
            model_id=selector,
            display_name=selector,
            planner_kind=planner_kind,
            wire_api=provider_entry.wire_api,
            supports_tools=True,
            supports_reasoning=resolved_supports_reasoning,
            supported_reasoning_efforts=resolved_supported_reasoning_efforts,
            default_reasoning_effort=resolved_default_reasoning_effort,
            reasoning_mode="reasoning_content" if "reasoner" in selector.lower() else "",
            reasoning_output_field="reasoning_content" if "reasoner" in selector.lower() else "",
            raw_model={},
        )
        if not provider_entry.default_model:
            provider_entry.default_model = unique_key


def find_model_entry(
    selector: str,
    catalog: Any,
    *,
    preferred_provider: Optional[str] = None,
) -> Any:
    token = str(selector or "").strip()
    if not token:
        return None
    direct = catalog.models.get(token)
    if direct is not None and (preferred_provider is None or direct.provider_name == preferred_provider):
        return direct
    normalized = token.lower()
    candidates = [
        entry
        for entry in catalog.models.values()
        if entry.key.lower() == normalized or entry.model_id.lower() == normalized
    ]
    if preferred_provider:
        for candidate in candidates:
            if candidate.provider_name == preferred_provider:
                return candidate
        return None
    return candidates[0] if candidates else None


def default_model_entry(
    provider_name: str,
    catalog: Any,
    *,
    find_model_entry_fn: Callable[..., Any] = find_model_entry,
) -> Any:
    provider_entry = catalog.providers.get(provider_name)
    if provider_entry is None:
        return None
    if provider_entry.default_model:
        entry = find_model_entry_fn(provider_entry.default_model, catalog, preferred_provider=provider_name)
        if entry is not None:
            return entry
    return next((entry for entry in catalog.models.values() if entry.provider_name == provider_name), None)
