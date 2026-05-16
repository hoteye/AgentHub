from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.config.catalog import (
    default_reasoning_effort_for_model,
    supported_reasoning_efforts_for_model,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.config_catalog_types import read_json_file as _read_json_file_impl

logger = logging.getLogger("cli.agent_cli.providers.anthropic_claude_runtime")
DEFAULT_CLAUDE_PROVIDER_ALIASES = frozenset(
    {"anthropic", "claude", "claude_code", "anthropic_claude"}
)
_CLAUDE_ALIAS_MODEL_KEYS = frozenset({"haiku", "sonnet", "opus"})


@dataclass(frozen=True)
class ClaudeConfigPaths:
    settings_path: Path
    config_path: Path
    state_path: Path


def claude_config_paths(home_dir: Path | None = None) -> ClaudeConfigPaths:
    home = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    return ClaudeConfigPaths(
        settings_path=home / ".claude" / "settings.json",
        config_path=home / ".claude" / "config.json",
        state_path=home / ".claude.json",
    )


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = _read_json_file_impl(path)
    except Exception as exc:
        logger.warning("Failed to read JSON file %s: %s", path, exc)
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def is_claude_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized.startswith("claude")


def _claude_model_alias(model: str) -> str:
    normalized = str(model or "").strip().lower()
    if normalized.startswith("claude-"):
        if "haiku" in normalized:
            return "haiku"
        if "sonnet" in normalized:
            return "sonnet"
        if "opus" in normalized:
            return "opus"
    if normalized in {"haiku", "haiku[1m]"}:
        return "haiku"
    if normalized in {"sonnet", "sonnet[1m]"}:
        return "sonnet"
    if normalized in {"opus", "opus[1m]"}:
        return "opus"
    return ""


def _is_supported_claude_selection(model: str) -> bool:
    return bool(is_claude_model(model) or _claude_model_alias(model))


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _default_model_for_alias(
    alias: str,
    *,
    env_mapping: Mapping[str, str],
    settings_env_mapping: Mapping[str, Any],
) -> str:
    normalized = _claude_model_alias(alias)
    if normalized == "haiku":
        return _first_text(
            env_mapping.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
            settings_env_mapping.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
        )
    if normalized == "sonnet":
        return _first_text(
            env_mapping.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
            settings_env_mapping.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
        )
    if normalized == "opus":
        return _first_text(
            env_mapping.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
            settings_env_mapping.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        )
    return ""


def _configured_claude_model(
    value: Any,
    *,
    env_mapping: Mapping[str, str],
    settings_env_mapping: Mapping[str, Any],
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    mapped = _default_model_for_alias(
        text,
        env_mapping=env_mapping,
        settings_env_mapping=settings_env_mapping,
    )
    if mapped:
        return mapped
    if _claude_model_alias(text) and not is_claude_model(text):
        return ""
    return text


def should_use_claude_provider(
    *,
    env_mapping: Mapping[str, str],
    configured_provider: str = "",
    configured_model: str = "",
    selected_config: ProviderConfig | None = None,
    claude_provider_aliases: frozenset[str] = DEFAULT_CLAUDE_PROVIDER_ALIASES,
) -> bool:
    del env_mapping
    normalized_provider = str(configured_provider or "").strip().lower()
    if normalized_provider in claude_provider_aliases:
        return True
    if is_claude_model(configured_model):
        return True
    if selected_config is None:
        return False
    selected_provider = str(selected_config.provider_name or "").strip().lower()
    if selected_provider in claude_provider_aliases:
        return True
    return bool(
        is_claude_model(selected_config.model)
        or is_claude_model(selected_config.model_key)
        or str(selected_config.planner_kind or "").strip().lower() == "anthropic_messages"
        or str(selected_config.wire_api or "").strip().lower() == "anthropic_messages"
    )


def load_claude_provider_config(
    *,
    env_mapping: Mapping[str, str],
    config_paths: ClaudeConfigPaths,
    fallback_model: str = "",
    fallback_base_url: str = "",
    default_claude_model: str,
    default_max_tokens: int,
) -> ProviderConfig | None:
    settings_data = read_json_file(config_paths.settings_path)
    config_data = read_json_file(config_paths.config_path)
    state_data = read_json_file(config_paths.state_path)

    settings_env = settings_data.get("env")
    settings_env_mapping = dict(settings_env) if isinstance(settings_env, dict) else {}

    auth_token = _first_text(
        env_mapping.get("ANTHROPIC_AUTH_TOKEN"),
        settings_env_mapping.get("ANTHROPIC_AUTH_TOKEN"),
    )
    api_key = _first_text(
        env_mapping.get("ANTHROPIC_API_KEY"),
        settings_env_mapping.get("ANTHROPIC_API_KEY"),
        config_data.get("primaryApiKey"),
        config_data.get("apiKey"),
        config_data.get("anthropicApiKey"),
        config_data.get("api_key"),
    )
    credential = auth_token or api_key
    if not credential:
        return None

    selected_model = str(env_mapping.get("AGENT_CLI_MODEL") or "").strip()
    settings_model = str(settings_data.get("model") or "").strip()
    model = _first_text(
        _configured_claude_model(
            selected_model,
            env_mapping=env_mapping,
            settings_env_mapping=settings_env_mapping,
        ),
        _configured_claude_model(
            settings_env_mapping.get("ANTHROPIC_MODEL"),
            env_mapping=env_mapping,
            settings_env_mapping=settings_env_mapping,
        ),
        _configured_claude_model(
            settings_model,
            env_mapping=env_mapping,
            settings_env_mapping=settings_env_mapping,
        ),
        config_data.get("defaultModel"),
        config_data.get("model"),
        _configured_claude_model(
            fallback_model,
            env_mapping=env_mapping,
            settings_env_mapping=settings_env_mapping,
        ),
        default_claude_model,
    )
    base_url = _first_text(
        env_mapping.get("ANTHROPIC_BASE_URL"),
        settings_env_mapping.get("ANTHROPIC_BASE_URL"),
        config_data.get("baseURL"),
        config_data.get("baseUrl"),
        fallback_base_url,
    )
    reasoning_effort = (
        _first_text(
            env_mapping.get("AGENT_CLI_REASONING_EFFORT"),
            settings_env_mapping.get("AGENT_CLI_REASONING_EFFORT"),
            config_data.get("reasoningEffort"),
            config_data.get("reasoning_effort"),
        )
        or None
    )
    supported_reasoning_efforts = supported_reasoning_efforts_for_model(
        provider_name="anthropic",
        model_id=model,
    )
    default_reasoning_effort = default_reasoning_effort_for_model(
        provider_name="anthropic",
        model_id=model,
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        supported_reasoning_efforts=supported_reasoning_efforts,
    )
    normalized_reasoning_effort = str(reasoning_effort or "").strip().lower()
    if normalized_reasoning_effort not in supported_reasoning_efforts:
        reasoning_effort = default_reasoning_effort or None
    else:
        reasoning_effort = normalized_reasoning_effort

    max_tokens_raw = config_data.get("maxOutputTokens", config_data.get("max_tokens"))
    try:
        max_tokens = int(max_tokens_raw) if max_tokens_raw is not None else int(default_max_tokens)
    except Exception:
        max_tokens = int(default_max_tokens)

    raw_provider = {
        "api_key_env": "ANTHROPIC_AUTH_TOKEN" if auth_token else "ANTHROPIC_API_KEY",
        "auth_token_env": "ANTHROPIC_AUTH_TOKEN" if auth_token else "",
        "has_completed_onboarding": bool(state_data.get("hasCompletedOnboarding")),
        "settings_path": str(config_paths.settings_path),
        "config_path": str(config_paths.config_path),
        "state_path": str(config_paths.state_path),
    }
    raw_model = {
        "supports_tools": True,
        "supports_reasoning": bool(supported_reasoning_efforts),
        "supported_reasoning_efforts": list(supported_reasoning_efforts),
        "default_reasoning_effort": default_reasoning_effort,
        "max_output_tokens": max_tokens,
    }

    return ProviderConfig(
        model=model,
        api_key=credential,
        provider_name="anthropic",
        model_key=model,
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url=base_url or None,
        reasoning_effort=reasoning_effort,
        source="claude_home",
        config_path=str(config_paths.settings_path),
        auth_path=str(config_paths.config_path),
        raw_provider=raw_provider,
        raw_model=raw_model,
    )
