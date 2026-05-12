from __future__ import annotations

import time
from typing import Any

from cli.agent_cli.providers.auth_refresh_scheduler_runtime import RefreshDaemonHandle, RefreshProviderContext
from cli.agent_cli.providers.auth_session_runtime import AuthSession
from cli.agent_cli.providers.auth_token_store_runtime import FileAuthTokenStore
from cli.agent_cli.provider_persistence_paths_runtime import resolve_user_provider_auth_path
from cli.agent_cli.providers.wellknown_discovery_runtime import discover_wellknown_metadata
from cli.agent_cli.runtime_core import (
    provider_commands_auth_helpers_runtime as provider_auth_helpers_runtime,
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
from cli.agent_cli.slash_surface import surface_usage_text


AUTH_SUBCOMMANDS = {"status", "login", "refresh", "logout"}


def parse_generic_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    return provider_parsing_helpers_runtime.parse_generic_args(arg_text)


def auth_command_hint(
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
    return provider_projection_helpers_runtime.auth_command_hint(
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


def auth_usage_text() -> str:
    return provider_projection_helpers_runtime.auth_usage_text(
        surface_usage_text_fn=surface_usage_text,
    )


def is_truthy(value: Any) -> bool:
    return provider_parsing_helpers_runtime.is_truthy(value)


def safe_int(value: Any, default: int = 0) -> int:
    return provider_parsing_helpers_runtime.safe_int(value, default=default)


def provider_loader_kwargs(runtime: Any) -> dict[str, Any]:
    return provider_auth_helpers_runtime.provider_loader_kwargs(runtime)


def load_provider_catalog(runtime: Any) -> Any | None:
    return provider_auth_helpers_runtime.load_provider_catalog(runtime)


def provider_alias_maps(runtime: Any, *, catalog: Any) -> tuple[dict[str, set[str]], dict[str, str]]:
    return provider_auth_helpers_runtime.provider_alias_maps(runtime, catalog=catalog)


def resolve_context_auth_mode(auth_mode: Any, *, allowed_modes: set[str]) -> str:
    return provider_auth_helpers_runtime.resolve_context_auth_mode(
        auth_mode,
        allowed_modes=allowed_modes,
    )


def resolve_auth_provider_context(
    runtime: Any,
    *,
    provider_override: str,
    allowed_modes: set[str],
) -> dict[str, Any]:
    return provider_auth_helpers_runtime.resolve_auth_provider_context(
        runtime,
        provider_override=provider_override,
        default_auth_path=resolve_user_provider_auth_path(),
        allowed_modes=allowed_modes,
    )


def token_ref_from_auth(auth: dict[str, Any], *, override: str = "") -> str:
    return provider_auth_helpers_runtime.token_ref_from_auth(auth, override=override)


def scope_text(auth: dict[str, Any]) -> str:
    return provider_auth_helpers_runtime.scope_text(auth)


def resolve_oauth_endpoints(
    context: dict[str, Any],
    *,
    login_mode: str,
    force_discovery: bool,
    discovery_ttl_seconds: int,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    return provider_auth_helpers_runtime.resolve_oauth_endpoints(
        context,
        login_mode=login_mode,
        force_discovery=force_discovery,
        discovery_ttl_seconds=discovery_ttl_seconds,
        default_auth_path=resolve_user_provider_auth_path(),
        discover_wellknown_metadata_fn=discover_wellknown_metadata,
    )


def auth_store_for_context(context: dict[str, Any]) -> FileAuthTokenStore:
    return provider_auth_helpers_runtime.auth_store_for_context(
        context,
        default_auth_path=resolve_user_provider_auth_path(),
        store_factory=FileAuthTokenStore,
    )


def refresh_daemon_handle(runtime: Any) -> RefreshDaemonHandle:
    existing = getattr(runtime, "_auth_refresh_daemon_handle", None)
    if isinstance(existing, RefreshDaemonHandle):
        return existing
    handle = RefreshDaemonHandle()
    runtime._auth_refresh_daemon_handle = handle
    return handle


def build_auth_status_lines(
    *,
    subcommand: str,
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    next_action: str,
) -> list[str]:
    return provider_projection_helpers_runtime.build_auth_status_lines(
        subcommand=subcommand,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=next_action,
    )


def status_contract_for_non_session_mode(auth_mode: str) -> tuple[str, str]:
    return provider_auth_helpers_runtime.status_contract_for_non_session_mode(
        auth_mode,
        auth_command_hint_fn=auth_command_hint,
    )


def save_session_from_oauth_result(
    *,
    store: FileAuthTokenStore,
    context: dict[str, Any],
    token_ref: str,
    oauth_result: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> AuthSession:
    now_ts = float(time.time())
    expires_in = safe_int(oauth_result.get("expires_in"), 0)
    session = AuthSession(
        provider_name=str(context.get("config_provider_name") or ""),
        token_ref=token_ref,
        access_token=str(oauth_result.get("access_token") or "").strip(),
        refresh_token=str(oauth_result.get("refresh_token") or "").strip(),
        token_type=str(oauth_result.get("token_type") or "").strip(),
        scope=str(oauth_result.get("scope") or "").strip(),
        expires_at=(now_ts + expires_in) if expires_in > 0 else None,
        issued_at=now_ts,
        metadata=dict(metadata or {}),
    )
    store.put(session)
    return session


def collect_refresh_contexts(runtime: Any, *, provider_filter: str) -> list[RefreshProviderContext]:
    return provider_auth_helpers_runtime.collect_refresh_contexts(
        runtime,
        provider_filter=provider_filter,
        refresh_provider_context_factory=RefreshProviderContext,
    )


def handle_auth_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: Any | None,
    command_module: Any,
) -> tuple[str, list]:
    return provider_commands_facade_runtime.handle_auth_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        command_module=command_module,
        auth_subcommands=AUTH_SUBCOMMANDS,
    )
