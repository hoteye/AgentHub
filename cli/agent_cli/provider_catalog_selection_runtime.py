from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.config.catalog import ProviderConfig


def _normalized_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_anthropic_messages_config(config: ProviderConfig | None) -> bool:
    if config is None:
        return False
    return (
        _normalized_text(config.planner_kind) == "anthropic_messages"
        or _normalized_text(config.wire_api) == "anthropic_messages"
    )


def _matches_selected_selector(selected: ProviderConfig | None, selector: str) -> bool:
    token = _normalized_text(selector)
    if not token or selected is None:
        return False
    return token in {
        _normalized_text(selected.provider_name),
        _normalized_text(selected.model_key),
        _normalized_text(selected.model),
    }


def _has_explicit_catalog_payload(config: ProviderConfig | None) -> bool:
    if config is None:
        return False
    provider_payload = {
        key: value
        for key, value in dict(config.raw_provider or {}).items()
        if key
        not in {
            "api_key_env",
            "auth_token_env",
            "no_auth_guardrail_reason",
            "no_auth_guardrail_pass",
            "auth_status",
            "token_source",
        }
    }
    model_payload = {
        key: value
        for key, value in dict(config.raw_model or {}).items()
        if key
        not in {
            "supports_reasoning",
            "supported_reasoning_efforts",
            "default_reasoning_effort",
            "reasoning_effort",
        }
    }
    return bool(provider_payload or model_payload)


def _should_prefer_explicit_selected_config(
    *,
    selected: ProviderConfig | None,
    configured_provider: str,
    configured_model: str,
) -> bool:
    if selected is None or _normalized_text(selected.source) == "claude_home":
        return False
    if not _is_anthropic_messages_config(selected):
        return False
    if not _has_explicit_catalog_payload(selected):
        return False
    return _matches_selected_selector(selected, configured_provider) or _matches_selected_selector(
        selected, configured_model
    )


def build_env_mapping(
    env_overrides: dict[str, str | None] | None = None,
) -> dict[str, str]:
    env_mapping: dict[str, str] = dict(os.environ)
    for key, value in dict(env_overrides or {}).items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if value is None:
            env_mapping.pop(normalized_key, None)
            continue
        env_mapping[normalized_key] = str(value)
    return env_mapping


def select_provider_config_from_inputs(
    *,
    resolution: Any,
    toml_data: dict[str, Any],
    auth_data: dict[str, Any],
    env_overrides: dict[str, str | None] | None = None,
    select_provider_config_fn: Callable[..., ProviderConfig | None],
    optional_bool_fn: Callable[[Any, bool], bool],
    infer_planner_kind_fn: Callable[[str, str, str | None, dict[str, Any]], str],
    should_use_claude_provider_fn: Callable[..., bool],
    project_claude_home_dir_fn: Callable[[], Path | None],
    load_claude_provider_config_fn: Callable[..., ProviderConfig | None],
) -> ProviderConfig | None:
    claude_provider_aliases = {
        "anthropic",
        "claude",
        "claude_code",
        "anthropic_claude",
    }
    env_mapping = build_env_mapping(env_overrides)
    env_selected_provider = str(env_mapping.get("AGENT_CLI_PROVIDER") or "").strip()
    env_selected_model = str(env_mapping.get("AGENT_CLI_MODEL") or "").strip()
    configured_provider = (
        env_selected_provider or str(toml_data.get("model_provider") or "").strip()
    )
    configured_model = env_selected_model or str(toml_data.get("model") or "").strip()
    selected = select_provider_config_fn(
        env_mapping=env_mapping,
        auth_data=auth_data,
        toml_data=toml_data,
        resolution=resolution,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
    )
    if env_selected_provider and env_selected_provider.lower() not in claude_provider_aliases:
        return selected
    if _should_prefer_explicit_selected_config(
        selected=selected,
        configured_provider=configured_provider,
        configured_model=configured_model,
    ):
        return selected
    if should_use_claude_provider_fn(
        env_mapping=env_mapping,
        configured_provider=configured_provider,
        configured_model=configured_model,
        selected_config=selected,
    ):
        explicit_claude_provider = str(configured_provider or "").strip().lower() in {
            *claude_provider_aliases,
        }
        selected_is_claude = bool(
            not explicit_claude_provider
            and selected is not None
            and (
                str(selected.model or "").strip().lower().startswith("claude")
                or str(selected.planner_kind or "").strip().lower() == "anthropic_messages"
                or str(selected.wire_api or "").strip().lower() == "anthropic_messages"
            )
        )
        configured_claude_model = (
            configured_model
            if str(configured_model or "").strip().lower().startswith("claude")
            else ""
        )
        project_claude_home_dir = project_claude_home_dir_fn()
        claude_config = load_claude_provider_config_fn(
            env_mapping=env_mapping,
            home_dir=project_claude_home_dir,
            fallback_model=configured_claude_model
            or (selected.model if selected_is_claude and selected is not None else ""),
            fallback_base_url=(
                str(selected.base_url or "") if selected_is_claude and selected is not None else ""
            ),
        )
        if claude_config is not None:
            return claude_config
    return selected


def load_provider_config(
    *,
    cwd: str | Path | None = None,
    env_overrides: dict[str, str | None] | None = None,
    load_provider_inputs_fn: Callable[..., tuple[Any, dict[str, Any], dict[str, Any]]],
    select_provider_config_fn: Callable[..., ProviderConfig | None],
    optional_bool_fn: Callable[[Any, bool], bool],
    infer_planner_kind_fn: Callable[[str, str, str | None, dict[str, Any]], str],
    should_use_claude_provider_fn: Callable[..., bool],
    project_claude_home_dir_fn: Callable[[], Path | None],
    load_claude_provider_config_fn: Callable[..., ProviderConfig | None],
) -> ProviderConfig | None:
    resolution, toml_data, auth_data = load_provider_inputs_fn(cwd=cwd)
    return select_provider_config_from_inputs(
        resolution=resolution,
        toml_data=toml_data,
        auth_data=auth_data,
        env_overrides=env_overrides,
        select_provider_config_fn=select_provider_config_fn,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
        should_use_claude_provider_fn=should_use_claude_provider_fn,
        project_claude_home_dir_fn=project_claude_home_dir_fn,
        load_claude_provider_config_fn=load_claude_provider_config_fn,
    )
