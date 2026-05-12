from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import provider_catalog_toml_runtime as provider_toml_runtime
from cli.agent_cli.provider_persistence_paths_runtime import (
    resolve_project_provider_config_write_path,
    resolve_user_provider_config_path,
)
from cli.agent_cli.runtime_core import (
    provider_commands_connect_helpers_runtime as provider_connect_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_facade_runtime as provider_commands_facade_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_parsing_helpers_runtime as provider_parsing_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_projection_helpers_runtime as provider_projection_helpers_runtime,
)
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set
from cli.agent_cli.slash_surface import surface_usage_text


CONNECT_VALUE_FLAGS = {
    "--provider",
    "--model",
    "--base-url",
    "--auth-mode",
    "--api-key-env",
    "--write",
}
CONNECT_BOOLEAN_FLAGS = {"--check"}
CONNECT_AUTH_MODES = {"api_key", "oauth", "wellknown", "none"}
CONNECT_WRITE_SCOPES = {"project", "user"}
SELECTION_WRITE_SCOPES = {"session", "user", "project"}
CONNECT_OFFICIAL_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "auth_mode": "api_key",
        "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "auth_mode": "api_key",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
}


def parse_connect_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    return provider_parsing_helpers_runtime.parse_flag_args(
        arg_text,
        value_flags=CONNECT_VALUE_FLAGS,
        boolean_flags=CONNECT_BOOLEAN_FLAGS,
    )


def slash_invocation_inputs(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], list[str], dict[str, Any], list[str]] | None:
    return provider_parsing_helpers_runtime.slash_invocation_inputs(
        slash_invocation,
        slash_keyword_map_fn=slash_keyword_map,
        slash_switch_set_fn=slash_switch_set,
    )


def slash_command_text(name: str, *parts: str) -> str:
    return provider_projection_helpers_runtime.slash_command_text(name, *parts)


def slugify_model_key(value: str) -> str:
    return provider_connect_helpers_runtime.slugify_model_key(value)


def provider_profile_name(*, provider_name: str, base_url: str) -> str:
    return provider_connect_helpers_runtime.provider_profile_name(
        provider_name,
        base_url=base_url,
    )


def upsert_provider_base_url(existing: str, *, provider_name: str, base_url: str) -> str:
    return provider_connect_helpers_runtime.upsert_provider_base_url(
        existing,
        provider_name=provider_name,
        base_url=base_url,
        quoted_toml_string_fn=provider_toml_runtime.quoted_toml_string,
    )


def upsert_provider_auth_fields(
    existing: str,
    *,
    provider_name: str,
    auth_mode: str,
    api_key_env: str,
) -> str:
    return provider_connect_helpers_runtime.upsert_provider_auth_fields(
        existing,
        provider_name=provider_name,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
        quoted_toml_string_fn=provider_toml_runtime.quoted_toml_string,
    )


def clear_connect_provider_fields(existing: str, *, provider_name: str, keys: tuple[str, ...] | list[str]) -> str:
    return provider_connect_helpers_runtime.clear_provider_fields(
        existing,
        provider_name=provider_name,
        keys=keys,
    )


def upsert_model_entry(existing: str, *, provider_name: str, model_selector: str) -> str:
    return provider_connect_helpers_runtime.upsert_model_entry(
        existing,
        provider_name=provider_name,
        model_selector=model_selector,
        quoted_toml_string_fn=provider_toml_runtime.quoted_toml_string,
    )


def resolve_connect_write_path(runtime: Any, write_scope: str) -> Path:
    if write_scope == "user":
        return resolve_user_provider_config_path()
    return resolve_project_provider_config_write_path(
        cwd=getattr(runtime, "cwd", None),
    )


def connect_usage_text() -> str:
    return provider_projection_helpers_runtime.connect_usage_text(
        surface_usage_text_fn=surface_usage_text,
    )


def connect_provider_defaults(provider_name: str) -> dict[str, str]:
    return provider_connect_helpers_runtime.connect_provider_defaults(
        provider_name,
        official_provider_defaults=CONNECT_OFFICIAL_PROVIDER_DEFAULTS,
    )


def resolved_connect_auth_mode(*, provider_name: str, auth_mode: str) -> str:
    return provider_connect_helpers_runtime.resolved_connect_auth_mode(
        provider_name=provider_name,
        auth_mode=auth_mode,
        official_provider_defaults=CONNECT_OFFICIAL_PROVIDER_DEFAULTS,
    )


def resolved_connect_api_key_env(*, provider_name: str, auth_mode: str, api_key_env: str) -> str:
    return provider_connect_helpers_runtime.resolved_connect_api_key_env(
        provider_name=provider_name,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
        official_provider_defaults=CONNECT_OFFICIAL_PROVIDER_DEFAULTS,
    )


def connect_requires_base_url(provider_name: str) -> bool:
    return provider_connect_helpers_runtime.connect_requires_base_url(
        provider_name,
        official_provider_defaults=CONNECT_OFFICIAL_PROVIDER_DEFAULTS,
    )


def connect_next_action_hint(
    *,
    provider_name: str,
    model_selector: str,
    base_url: str,
    auth_mode: str,
    api_key_env: str,
    write_scope: str,
) -> str:
    return provider_connect_helpers_runtime.connect_next_action_hint(
        provider_name=provider_name,
        model_selector=model_selector,
        base_url=base_url,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
        write_scope=write_scope,
        official_provider_defaults=CONNECT_OFFICIAL_PROVIDER_DEFAULTS,
    )


def handle_connect_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None,
    command_module: Any,
) -> tuple[str, list]:
    return provider_commands_facade_runtime.handle_connect_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        command_module=command_module,
        connect_auth_modes=CONNECT_AUTH_MODES,
        connect_write_scopes=CONNECT_WRITE_SCOPES,
    )
