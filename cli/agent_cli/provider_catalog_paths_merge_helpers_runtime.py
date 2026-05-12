from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.workspace_context import merge_nested_mappings


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _model_selection_matches_catalog(
    *,
    selection_provider: str,
    selection_model: str,
    configured_provider: str,
    configured_model: str,
    models_payload: Dict[str, Any],
) -> bool:
    if not selection_model:
        return False
    if selection_model == configured_model and (
        not selection_provider or selection_provider == configured_provider
    ):
        return True
    model_payload = models_payload.get(selection_model)
    if isinstance(model_payload, dict):
        model_provider = _normalized_text(model_payload.get("provider"))
        return not selection_provider or selection_provider == model_provider
    for model_key, raw_payload in models_payload.items():
        if not isinstance(raw_payload, dict):
            continue
        model_candidates = {
            _normalized_text(model_key),
            _normalized_text(raw_payload.get("model")),
            _normalized_text(raw_payload.get("model_id")),
        }
        if selection_model not in model_candidates:
            continue
        model_provider = _normalized_text(raw_payload.get("provider"))
        if not selection_provider or selection_provider == model_provider:
            return True
    return False


def _user_model_selection_matches_catalog(
    *,
    toml_data: Dict[str, Any],
    user_model_selection: Dict[str, Any],
) -> bool:
    selection_provider = _normalized_text(user_model_selection.get("model_provider"))
    selection_model = _normalized_text(user_model_selection.get("model"))
    if not selection_provider and not selection_model:
        return False
    configured_provider = _normalized_text(toml_data.get("model_provider"))
    configured_model = _normalized_text(toml_data.get("model"))
    model_providers = toml_data.get("model_providers")
    provider_payload = model_providers if isinstance(model_providers, dict) else {}
    models = toml_data.get("models")
    models_payload = models if isinstance(models, dict) else {}
    if (
        not configured_provider
        and not configured_model
        and not provider_payload
        and not models_payload
    ):
        return True
    provider_matches = (
        not selection_provider
        or selection_provider == configured_provider
        or selection_provider in provider_payload
        or any(
            selection_provider == _normalized_text(raw_payload.get("provider"))
            for raw_payload in models_payload.values()
            if isinstance(raw_payload, dict)
        )
    )
    model_matches = (
        not selection_model
        or _model_selection_matches_catalog(
            selection_provider=selection_provider,
            selection_model=selection_model,
            configured_provider=configured_provider,
            configured_model=configured_model,
            models_payload=models_payload,
        )
    )
    return provider_matches and model_matches


def _apply_user_model_selection(
    *,
    toml_data: Dict[str, Any],
    user_model_selection: Dict[str, Any],
) -> Dict[str, Any]:
    if not user_model_selection:
        return toml_data
    if not _user_model_selection_matches_catalog(
        toml_data=toml_data,
        user_model_selection=user_model_selection,
    ):
        return toml_data
    selection: Dict[str, Any] = {}
    configured_provider = _normalized_text(toml_data.get("model_provider"))
    configured_model = _normalized_text(toml_data.get("model"))
    provider_name = _normalized_text(user_model_selection.get("model_provider"))
    if provider_name:
        selection["model_provider"] = provider_name
    model_name = _normalized_text(user_model_selection.get("model"))
    if model_name:
        selection["model"] = model_name
    reasoning_effort = _normalized_text(user_model_selection.get("model_reasoning_effort"))
    selection_changes_target = (
        (provider_name and provider_name != configured_provider)
        or (model_name and model_name != configured_model)
    )
    if reasoning_effort and (
        selection_changes_target
        or not _normalized_text(toml_data.get("model_reasoning_effort"))
    ):
        selection["model_reasoning_effort"] = reasoning_effort
    if not selection:
        return toml_data
    return merge_nested_mappings(toml_data, selection)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _provider_profile_request(
    *,
    user_toml_data: Dict[str, Any],
    project_toml_data: Dict[str, Any],
    merged_toml_data: Dict[str, Any],
) -> tuple[str, str]:
    project_profile = _normalized_text(project_toml_data.get("provider_profile"))
    if project_profile:
        return project_profile, "project.provider_profile"
    project_default_profile = _normalized_text(project_toml_data.get("default_provider_profile"))
    if project_default_profile:
        return project_default_profile, "project.default_provider_profile"
    merged_profile = _normalized_text(merged_toml_data.get("provider_profile"))
    if merged_profile:
        return merged_profile, "merged.provider_profile"
    user_default_profile = _normalized_text(user_toml_data.get("default_provider_profile"))
    if user_default_profile:
        return user_default_profile, "user.default_provider_profile"
    return "", ""


def _materialize_provider_profile(
    *,
    user_toml_data: Dict[str, Any],
    project_toml_data: Dict[str, Any],
    merged_toml_data: Dict[str, Any],
) -> Dict[str, Any]:
    profile_name, profile_source = _provider_profile_request(
        user_toml_data=user_toml_data,
        project_toml_data=project_toml_data,
        merged_toml_data=merged_toml_data,
    )
    if not profile_name:
        return merged_toml_data
    profiles_payload = _mapping(merged_toml_data.get("provider_profiles"))
    raw_profile = _mapping(profiles_payload.get(profile_name))
    updated = dict(merged_toml_data)
    updated["provider_profile_active"] = profile_name
    updated["provider_profile_source"] = profile_source
    if not raw_profile:
        updated["provider_profile_missing"] = profile_name
        updated["model_provider"] = ""
        updated["model"] = ""
        return updated

    provider_name = _normalized_text(raw_profile.get("provider") or raw_profile.get("provider_name"))
    profile_model = _normalized_text(raw_profile.get("model") or raw_profile.get("model_id"))
    if provider_name:
        updated["model_provider"] = provider_name
    explicit_project_model = _normalized_text(project_toml_data.get("model"))
    if explicit_project_model:
        updated["model"] = explicit_project_model
    elif profile_model:
        updated["model"] = profile_model

    provider_profiles_reserved = {
        "provider",
        "provider_name",
        "model",
        "model_id",
    }
    profile_provider_block = {
        key: value
        for key, value in raw_profile.items()
        if key not in provider_profiles_reserved
    }
    if provider_name and profile_provider_block:
        merged_provider_payload = _mapping(updated.get("model_providers"))
        existing_provider_block = _mapping(merged_provider_payload.get(provider_name))
        merged_provider_payload[provider_name] = merge_nested_mappings(
            profile_provider_block,
            existing_provider_block,
        )
        updated["model_providers"] = merged_provider_payload
    return updated
