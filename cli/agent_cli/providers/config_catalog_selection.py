from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.providers import config_catalog_selection_auth_runtime as _auth_runtime
from cli.agent_cli.providers import security_endpoint_classify_runtime as endpoint_security_runtime
from cli.agent_cli.providers.config_catalog_types import (
    ProviderConfig,
    ProviderPathResolution,
    build_provider_catalog,
    default_model_entry,
    default_reasoning_effort_for_model,
    find_model_entry,
    infer_planner_kind,
    optional_bool,
    reasoning_effort_supported_for_model,
    resolve_model_migration,
    supported_reasoning_efforts_for_model,
)
from cli.agent_cli.providers.interaction_profile_config import (
    resolve_configured_interaction_profile,
)

candidate_api_key_names = _auth_runtime.candidate_api_key_names
first_configured_key = _auth_runtime.first_configured_key
first_configured_key_name = _auth_runtime.first_configured_key_name
_first_env_value = _auth_runtime._first_env_value
_is_truthy = _auth_runtime._is_truthy
_aliased_mapping_value = _auth_runtime._aliased_mapping_value
_resolve_token_ref = _auth_runtime._resolve_token_ref
_session_from_payload = _auth_runtime._session_from_payload
_resolve_oauth_access_token = _auth_runtime._resolve_oauth_access_token


def resolve_provider_paths(
    *,
    project_auth_path: Path | None,
    project_config_path: Path | None,
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
) -> ProviderPathResolution:
    if project_auth_path or project_config_path:
        auth_path = project_auth_path or (project_config_path.parent / "auth.json")
        config_path = project_config_path or (project_auth_path.parent / "config.toml")
    elif agent_cli_config_toml.exists() or agent_cli_auth_json.exists():
        auth_path = agent_cli_auth_json
        config_path = agent_cli_config_toml
    else:
        auth_path = legacy_compat_auth_json
        config_path = legacy_compat_config_toml
    return ProviderPathResolution(
        config_path=config_path,
        auth_path=auth_path,
        config_exists=config_path.exists(),
        auth_exists=auth_path.exists(),
        used_project_local=bool(project_auth_path or project_config_path),
    )


def select_provider_config(
    *,
    env_mapping: Mapping[str, str],
    auth_data: dict[str, Any],
    toml_data: dict[str, Any],
    resolution: ProviderPathResolution,
    optional_bool_fn: Callable[[Any, bool], bool] = optional_bool,
    infer_planner_kind_fn: Callable[
        [str, str, str | None, dict[str, Any]], str
    ] = infer_planner_kind,
) -> ProviderConfig | None:
    env_provider = str(env_mapping.get("AGENT_CLI_PROVIDER", "")).strip()
    provider_hint = env_provider or str(toml_data.get("model_provider") or "").strip()
    if provider_hint.lower() == "anthropic":
        env_model = _first_env_value(
            env_mapping, "AGENT_CLI_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL"
        )
        env_base_url = _first_env_value(
            env_mapping, "AGENT_CLI_BASE_URL", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"
        )
        env_reasoning = _first_env_value(
            env_mapping,
            "AGENT_CLI_REASONING_EFFORT",
            "ANTHROPIC_REASONING_EFFORT",
            "OPENAI_REASONING_EFFORT",
        )
    else:
        env_model = _first_env_value(env_mapping, "AGENT_CLI_MODEL", "OPENAI_MODEL")
        env_base_url = _first_env_value(env_mapping, "AGENT_CLI_BASE_URL", "OPENAI_BASE_URL")
        env_reasoning = _first_env_value(
            env_mapping, "AGENT_CLI_REASONING_EFFORT", "OPENAI_REASONING_EFFORT"
        )

    catalog = build_provider_catalog(
        toml_data,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
    )
    requested_provider = env_provider or str(toml_data.get("model_provider") or "").strip()
    configured_model = env_model or str(toml_data.get("model") or "").strip()
    requested_model = resolve_model_migration(configured_model, toml_data)
    selected_model_entry = find_model_entry(
        requested_model, catalog, preferred_provider=requested_provider or None
    )

    provider_name = requested_provider or (
        selected_model_entry.provider_name if selected_model_entry is not None else ""
    )
    provider_entry = catalog.providers.get(provider_name)
    provider_block: dict[str, Any] = (
        dict(provider_entry.raw_provider) if provider_entry is not None else {}
    )
    if provider_entry is not None:
        merged_auth = dict(provider_entry.auth)
        raw_auth = provider_block.get("auth")
        if isinstance(raw_auth, Mapping):
            merged_auth = {**dict(raw_auth), **merged_auth}
        if merged_auth:
            provider_block["auth"] = merged_auth

    if selected_model_entry is None and provider_name:
        selected_model_entry = default_model_entry(provider_name, catalog)
    elif (
        selected_model_entry is not None
        and provider_name
        and selected_model_entry.provider_name != provider_name
    ):
        selected_model_entry = find_model_entry(
            requested_model, catalog, preferred_provider=provider_name
        )
        if selected_model_entry is None:
            selected_model_entry = default_model_entry(provider_name, catalog)

    raw_model = dict(selected_model_entry.raw_model) if selected_model_entry is not None else {}
    model = (
        (selected_model_entry.model_id if selected_model_entry is not None else "")
        or env_model
        or requested_model
        or str(provider_block.get("model") or "").strip()
    )
    base_url = (
        env_base_url
        or str(raw_model.get("base_url") or "").strip()
        or str(provider_block.get("base_url") or "").strip()
        or None
    )
    configured_reasoning_effort = (
        env_reasoning
        or str(raw_model.get("reasoning_effort") or "").strip()
        or str(
            provider_block.get("reasoning_effort") or toml_data.get("model_reasoning_effort") or ""
        ).strip()
    )
    reasoning_effort = configured_reasoning_effort or None
    candidate_key_names = candidate_api_key_names(provider_name, provider_block, model, base_url)
    env_key_name = first_configured_key_name(env_mapping, candidate_key_names)
    auth_key_name = (
        "" if env_key_name else first_configured_key_name(auth_data, candidate_key_names)
    )
    api_key_name = env_key_name or auth_key_name
    api_key = first_configured_key(env_mapping, candidate_key_names) or first_configured_key(
        auth_data, candidate_key_names
    )
    planner_context = {**provider_block, **raw_model}
    planner_kind = infer_planner_kind_fn(provider_name, model, base_url, planner_context)
    wire_api = (
        str(raw_model.get("wire_api") or provider_block.get("wire_api") or "").strip().lower()
    )
    auth_mode = str(provider_block.get("auth_mode") or "api_key").strip().lower() or "api_key"
    auth = (
        dict(provider_block.get("auth") or {})
        if isinstance(provider_block.get("auth"), dict)
        else {}
    )
    injected_token, auth_status, token_source = _resolve_oauth_access_token(
        provider_name=provider_name,
        provider_block=provider_block,
        auth_mode=auth_mode,
        auth_data=auth_data,
        auth_path=resolution.auth_path if resolution is not None else None,
    )
    if not api_key and injected_token:
        api_key = injected_token
    allow_no_auth = _is_truthy(provider_block.get("allow_no_auth"))
    guardrail_reason = endpoint_security_runtime.no_auth_guardrail_reason(
        auth_mode=auth_mode,
        allow_no_auth=allow_no_auth,
        base_url=base_url,
    )
    no_auth_guardrail_pass = endpoint_security_runtime.no_auth_guardrail_pass(
        auth_mode=auth_mode,
        allow_no_auth=allow_no_auth,
        base_url=base_url,
    )
    if not model:
        return None
    if not api_key and auth_mode == "api_key":
        auth_status = auth_status or "missing"
    elif not api_key and not no_auth_guardrail_pass:
        return None

    if (
        any(str(env_mapping.get(name, "")).strip() for name in candidate_key_names)
        or env_model
        or env_base_url
        or env_reasoning
        or env_provider
    ):
        source = "env"
    elif resolution.used_project_local:
        source = "project_local"
    else:
        source = "agent_cli_home"

    projected_provider_block = dict(provider_block)
    if api_key_name == "ANTHROPIC_AUTH_TOKEN":
        projected_provider_block["api_key_env"] = "ANTHROPIC_AUTH_TOKEN"
        projected_provider_block["auth_token_env"] = "ANTHROPIC_AUTH_TOKEN"
    projected_provider_block["no_auth_guardrail_reason"] = guardrail_reason
    projected_provider_block["no_auth_guardrail_pass"] = bool(no_auth_guardrail_pass)
    if auth_status:
        projected_provider_block["auth_status"] = auth_status
    if token_source:
        projected_provider_block["token_source"] = token_source
    interaction_profile, interaction_profile_source = resolve_configured_interaction_profile(
        raw_model=raw_model,
        raw_provider=projected_provider_block,
    )
    supported_reasoning_efforts = (
        selected_model_entry.supported_reasoning_efforts
        if selected_model_entry is not None
        else supported_reasoning_efforts_for_model(
            provider_name=provider_name,
            model_id=model,
            supports_reasoning=raw_model.get("supports_reasoning"),
            reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
            reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
            supported_reasoning_efforts=_aliased_mapping_value(
                raw_model, "supported_reasoning_efforts", "supportedReasoningEfforts"
            ),
            default_reasoning_effort=_aliased_mapping_value(
                raw_model, "default_reasoning_effort", "defaultReasoningEffort"
            ),
        )
    )
    default_reasoning_effort = default_reasoning_effort_for_model(
        provider_name=provider_name,
        model_id=model,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
        supports_reasoning=(
            selected_model_entry.supports_reasoning
            if selected_model_entry is not None
            else raw_model.get("supports_reasoning")
        ),
        reasoning_mode=(
            str(selected_model_entry.reasoning_mode or "").strip()
            if selected_model_entry is not None
            else str(raw_model.get("reasoning_mode") or "").strip()
        ),
        reasoning_output_field=(
            str(selected_model_entry.reasoning_output_field or "").strip()
            if selected_model_entry is not None
            else str(raw_model.get("reasoning_output_field") or "").strip()
        ),
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=(
            selected_model_entry.default_reasoning_effort
            if selected_model_entry is not None
            else _aliased_mapping_value(
                raw_model, "default_reasoning_effort", "defaultReasoningEffort"
            )
        ),
    )
    normalized_configured_reasoning_effort = str(configured_reasoning_effort or "").strip().lower()
    if normalized_configured_reasoning_effort and reasoning_effort_supported_for_model(
        normalized_configured_reasoning_effort,
        provider_name=provider_name,
        model_id=model,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
        supports_reasoning=(
            selected_model_entry.supports_reasoning
            if selected_model_entry is not None
            else raw_model.get("supports_reasoning")
        ),
        reasoning_mode=str(raw_model.get("reasoning_mode") or "").strip(),
        reasoning_output_field=str(raw_model.get("reasoning_output_field") or "").strip(),
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
    ):
        reasoning_effort = normalized_configured_reasoning_effort
    elif default_reasoning_effort:
        reasoning_effort = default_reasoning_effort
    else:
        reasoning_effort = None
    raw_model["supports_reasoning"] = (
        selected_model_entry.supports_reasoning
        if selected_model_entry is not None
        else bool(raw_model.get("supports_reasoning"))
    )
    raw_model["supported_reasoning_efforts"] = list(supported_reasoning_efforts)
    raw_model["default_reasoning_effort"] = default_reasoning_effort
    if reasoning_effort:
        raw_model["reasoning_effort"] = reasoning_effort
    else:
        raw_model.pop("reasoning_effort", None)

    return ProviderConfig(
        model=model,
        api_key=api_key,
        provider_name=provider_name,
        model_key=selected_model_entry.key if selected_model_entry is not None else "",
        planner_kind=planner_kind,
        wire_api=wire_api,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
        source=source,
        config_path=str(resolution.config_path),
        auth_path=str(resolution.auth_path),
        auth_mode=auth_mode,
        auth=auth,
        auth_status=auth_status,
        token_source=token_source,
        interaction_profile=interaction_profile,
        interaction_profile_source=interaction_profile_source,
        raw_provider=projected_provider_block,
        raw_model=raw_model,
    )
