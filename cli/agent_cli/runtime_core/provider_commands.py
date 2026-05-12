from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli import provider_catalog_toml_runtime as provider_toml_runtime
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.auth_refresh_daemon_process_runtime import (
    managed_refresh_daemon_status,
    start_managed_refresh_daemon,
    stop_managed_refresh_daemon,
)
from cli.agent_cli.providers.auth_refresh_scheduler_runtime import (
    RefreshDaemonHandle,
    RefreshProviderContext,
    refresh_daemon_status,
    refresh_due_sessions,
    start_refresh_daemon,
    stop_refresh_daemon,
)
from cli.agent_cli.providers.auth_session_runtime import (
    AuthSession,
    auth_session_status,
    ensure_auth_session_status,
)
from cli.agent_cli.providers.auth_token_store_runtime import FileAuthTokenStore
from cli.agent_cli.providers.oauth_device_flow_runtime import (
    poll_device_flow,
    refresh_oauth_token,
    start_device_flow,
)
from cli.agent_cli.providers.oauth_pkce_callback_runtime import wait_for_pkce_callback
from cli.agent_cli.providers.oauth_pkce_runtime import (
    exchange_pkce_authorization_code,
    start_pkce_authorization,
)
from cli.agent_cli.provider_persistence_paths_runtime import (
    resolve_project_provider_config_write_path,
    resolve_user_provider_auth_path,
    resolve_user_provider_config_path,
)
from cli.agent_cli.runtime_core import (
    provider_commands_auth_helpers_runtime as provider_auth_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_auth_patchpoint_helpers_runtime as provider_auth_patchpoints_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_connect_patchpoint_helpers_runtime as provider_connect_patchpoints_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_facade_runtime as provider_commands_facade_runtime,
)
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set

_CONNECT_VALUE_FLAGS = provider_connect_patchpoints_runtime.CONNECT_VALUE_FLAGS
_CONNECT_BOOLEAN_FLAGS = provider_connect_patchpoints_runtime.CONNECT_BOOLEAN_FLAGS
_CONNECT_AUTH_MODES = provider_connect_patchpoints_runtime.CONNECT_AUTH_MODES
_CONNECT_WRITE_SCOPES = provider_connect_patchpoints_runtime.CONNECT_WRITE_SCOPES
_SELECTION_WRITE_SCOPES = provider_connect_patchpoints_runtime.SELECTION_WRITE_SCOPES
_CONNECT_OFFICIAL_PROVIDER_DEFAULTS = provider_connect_patchpoints_runtime.CONNECT_OFFICIAL_PROVIDER_DEFAULTS
_AUTH_SUBCOMMANDS = provider_auth_patchpoints_runtime.AUTH_SUBCOMMANDS
_CURRENT_MODULE = sys.modules[__name__]
_COMPAT_PATCHPOINTS = (
    managed_refresh_daemon_status,
    start_managed_refresh_daemon,
    stop_managed_refresh_daemon,
    refresh_daemon_status,
    refresh_due_sessions,
    start_refresh_daemon,
    stop_refresh_daemon,
    auth_session_status,
    ensure_auth_session_status,
    poll_device_flow,
    refresh_oauth_token,
    start_device_flow,
    wait_for_pkce_callback,
    exchange_pkce_authorization_code,
    start_pkce_authorization,
)


def _parse_connect_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    return provider_connect_patchpoints_runtime.parse_connect_args(arg_text)


def _parse_generic_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    return provider_auth_patchpoints_runtime.parse_generic_args(arg_text)


def _slash_invocation_inputs(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], list[str], dict[str, Any], list[str]] | None:
    return provider_connect_patchpoints_runtime.slash_invocation_inputs(slash_invocation)


def _slash_command_text(name: str, *parts: str) -> str:
    return provider_connect_patchpoints_runtime.slash_command_text(name, *parts)


def _auth_command_hint(
    action: str,
    *,
    provider_name: str = "",
    mode: str = "",
    poll: bool = False,
    auth_code: str = "",
    state: str = "",
    auto: bool = False,
    daemon: str = "",
    managed: bool = False,
) -> str:
    return provider_auth_patchpoints_runtime.auth_command_hint(
        action,
        provider_name=provider_name,
        mode=mode,
        poll=poll,
        auth_code=auth_code,
        state=state,
        auto=auto,
        daemon=daemon,
        managed=managed,
    )


def _slugify_model_key(value: str) -> str:
    return provider_connect_patchpoints_runtime.slugify_model_key(value)


def _provider_profile_name(*, provider_name: str, base_url: str) -> str:
    return provider_connect_patchpoints_runtime.provider_profile_name(
        provider_name=provider_name,
        base_url=base_url,
    )


def _upsert_provider_base_url(existing: str, *, provider_name: str, base_url: str) -> str:
    return provider_connect_patchpoints_runtime.upsert_provider_base_url(
        existing,
        provider_name=provider_name,
        base_url=base_url,
    )


def _upsert_provider_auth_fields(
    existing: str,
    *,
    provider_name: str,
    auth_mode: str,
    api_key_env: str,
) -> str:
    return provider_connect_patchpoints_runtime.upsert_provider_auth_fields(
        existing,
        provider_name=provider_name,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
    )


def _clear_connect_provider_fields(existing: str, *, provider_name: str, keys: tuple[str, ...] | list[str]) -> str:
    return provider_connect_patchpoints_runtime.clear_connect_provider_fields(
        existing,
        provider_name=provider_name,
        keys=keys,
    )


def _upsert_model_entry(existing: str, *, provider_name: str, model_selector: str) -> str:
    return provider_connect_patchpoints_runtime.upsert_model_entry(
        existing,
        provider_name=provider_name,
        model_selector=model_selector,
    )


def _resolve_connect_write_path(runtime: Any, write_scope: str) -> Path:
    if write_scope == "user":
        return resolve_user_provider_config_path()
    return resolve_project_provider_config_write_path(
        cwd=getattr(runtime, "cwd", None),
    )


def _connect_usage_text() -> str:
    return provider_connect_patchpoints_runtime.connect_usage_text()


def _connect_provider_defaults(provider_name: str) -> dict[str, str]:
    return provider_connect_patchpoints_runtime.connect_provider_defaults(provider_name)


def _resolved_connect_auth_mode(*, provider_name: str, auth_mode: str) -> str:
    return provider_connect_patchpoints_runtime.resolved_connect_auth_mode(
        provider_name=provider_name,
        auth_mode=auth_mode,
    )


def _resolved_connect_api_key_env(*, provider_name: str, auth_mode: str, api_key_env: str) -> str:
    return provider_connect_patchpoints_runtime.resolved_connect_api_key_env(
        provider_name=provider_name,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
    )


def _connect_requires_base_url(provider_name: str) -> bool:
    return provider_connect_patchpoints_runtime.connect_requires_base_url(provider_name)


def _connect_next_action_hint(
    *,
    provider_name: str,
    model_selector: str,
    base_url: str,
    auth_mode: str,
    api_key_env: str,
    write_scope: str,
) -> str:
    return provider_connect_patchpoints_runtime.connect_next_action_hint(
        provider_name=provider_name,
        model_selector=model_selector,
        base_url=base_url,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
        write_scope=write_scope,
    )


def _handle_connect_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list]:
    return provider_connect_patchpoints_runtime.handle_connect_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        command_module=_CURRENT_MODULE,
    )


def _auth_usage_text() -> str:
    return provider_auth_patchpoints_runtime.auth_usage_text()


def _is_truthy(value: Any) -> bool:
    return provider_auth_patchpoints_runtime.is_truthy(value)


def _safe_int(value: Any, default: int = 0) -> int:
    return provider_auth_patchpoints_runtime.safe_int(value, default=default)


def _provider_loader_kwargs(runtime: Any) -> dict[str, Any]:
    return provider_auth_patchpoints_runtime.provider_loader_kwargs(runtime)


def _load_provider_catalog(runtime: Any) -> Any | None:
    return provider_auth_patchpoints_runtime.load_provider_catalog(runtime)


def _provider_alias_maps(runtime: Any, *, catalog: Any) -> tuple[dict[str, set[str]], dict[str, str]]:
    return provider_auth_patchpoints_runtime.provider_alias_maps(runtime, catalog=catalog)


def _resolve_context_auth_mode(auth_mode: Any) -> str:
    return provider_auth_patchpoints_runtime.resolve_context_auth_mode(
        auth_mode,
        allowed_modes=_CONNECT_AUTH_MODES,
    )


def _resolve_auth_provider_context(runtime: Any, *, provider_override: str) -> dict[str, Any]:
    return provider_auth_patchpoints_runtime.resolve_auth_provider_context(
        runtime,
        provider_override=provider_override,
        allowed_modes=_CONNECT_AUTH_MODES,
    )


def _token_ref_from_auth(auth: dict[str, Any], *, override: str = "") -> str:
    return provider_auth_patchpoints_runtime.token_ref_from_auth(auth, override=override)


def _scope_text(auth: dict[str, Any]) -> str:
    return provider_auth_patchpoints_runtime.scope_text(auth)


def _resolve_oauth_endpoints(
    context: dict[str, Any],
    *,
    login_mode: str,
    force_discovery: bool,
    discovery_ttl_seconds: int,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    return provider_auth_patchpoints_runtime.resolve_oauth_endpoints(
        context,
        login_mode=login_mode,
        force_discovery=force_discovery,
        discovery_ttl_seconds=discovery_ttl_seconds,
    )


def _auth_store_for_context(context: dict[str, Any]) -> FileAuthTokenStore:
    return provider_auth_patchpoints_runtime.auth_store_for_context(context)


def _refresh_daemon_handle(runtime: Any) -> RefreshDaemonHandle:
    return provider_auth_patchpoints_runtime.refresh_daemon_handle(runtime)


def _build_auth_status_lines(
    *,
    subcommand: str,
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    next_action: str,
) -> list[str]:
    return provider_auth_patchpoints_runtime.build_auth_status_lines(
        subcommand=subcommand,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=next_action,
    )


def _status_contract_for_non_session_mode(auth_mode: str) -> tuple[str, str]:
    return provider_auth_patchpoints_runtime.status_contract_for_non_session_mode(auth_mode)


def _save_session_from_oauth_result(
    *,
    store: FileAuthTokenStore,
    context: dict[str, Any],
    token_ref: str,
    oauth_result: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> AuthSession:
    return provider_auth_patchpoints_runtime.save_session_from_oauth_result(
        store=store,
        context=context,
        token_ref=token_ref,
        oauth_result=oauth_result,
        metadata=metadata,
    )


def _collect_refresh_contexts(runtime: Any, *, provider_filter: str) -> list[RefreshProviderContext]:
    return provider_auth_patchpoints_runtime.collect_refresh_contexts(
        runtime,
        provider_filter=provider_filter,
    )


def _handle_auth_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list]:
    return provider_auth_patchpoints_runtime.handle_auth_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        command_module=_CURRENT_MODULE,
    )


def handle_provider_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[ToolEvent]]],
    slash_invocation: Any | None = None,
) -> tuple[str, list[ToolEvent]] | None:
    return provider_commands_facade_runtime.handle_provider_command(
        runtime,
        name=name,
        arg_text=arg_text,
        switch_disabled_result=switch_disabled_result,
        slash_invocation=slash_invocation,
        command_module=_CURRENT_MODULE,
    )
