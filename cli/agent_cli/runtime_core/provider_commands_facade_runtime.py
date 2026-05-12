from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core import (
    provider_commands_auth_flow_runtime as provider_auth_flow_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_connect_flow_runtime as provider_connect_flow_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_dispatch_helpers_runtime as provider_dispatch_helpers_runtime,
)
from cli.agent_cli.runtime_core.provider_catalog_commands_runtime import (
    handle_models_cache_status_command,
    handle_models_refresh_command,
)
from cli.agent_cli.runtime_services import (
    provider_availability_refresh_runtime as provider_availability_refresh_runtime_service,
)


def _command_attr(command_module: Any, name: str) -> Any:
    return getattr(command_module, name)


def _connect_command_deps(command_module: Any) -> dict[str, Any]:
    provider_toml_runtime = _command_attr(command_module, "provider_toml_runtime")
    return {
        "parse_connect_args_fn": _command_attr(command_module, "_parse_connect_args"),
        "slash_invocation_inputs_fn": _command_attr(command_module, "_slash_invocation_inputs"),
        "connect_usage_text_fn": _command_attr(command_module, "_connect_usage_text"),
        "resolved_connect_auth_mode_fn": _command_attr(command_module, "_resolved_connect_auth_mode"),
        "resolved_connect_api_key_env_fn": _command_attr(
            command_module,
            "_resolved_connect_api_key_env",
        ),
        "connect_requires_base_url_fn": _command_attr(command_module, "_connect_requires_base_url"),
        "connect_next_action_hint_fn": _command_attr(command_module, "_connect_next_action_hint"),
        "resolve_connect_write_path_fn": _command_attr(command_module, "_resolve_connect_write_path"),
        "save_user_model_selection_fn": provider_toml_runtime.save_user_model_selection,
        "load_toml_document_text_fn": provider_toml_runtime.load_toml_document_text,
        "write_toml_document_text_fn": provider_toml_runtime.write_toml_document_text,
        "upsert_provider_profile_fn": provider_toml_runtime.upsert_provider_profile,
        "provider_profile_name_fn": _command_attr(command_module, "_provider_profile_name"),
        "upsert_provider_base_url_fn": _command_attr(command_module, "_upsert_provider_base_url"),
        "upsert_provider_auth_fields_fn": _command_attr(
            command_module,
            "_upsert_provider_auth_fields",
        ),
        "clear_connect_provider_fields_fn": _command_attr(
            command_module,
            "_clear_connect_provider_fields",
        ),
        "upsert_model_entry_fn": _command_attr(command_module, "_upsert_model_entry"),
        "slash_command_text_fn": _command_attr(command_module, "_slash_command_text"),
    }


def _auth_command_deps(command_module: Any) -> dict[str, Any]:
    return {
        "slash_invocation_inputs_fn": _command_attr(command_module, "_slash_invocation_inputs"),
        "parse_generic_args_fn": _command_attr(command_module, "_parse_generic_args"),
        "auth_usage_text_fn": _command_attr(command_module, "_auth_usage_text"),
        "resolve_auth_provider_context_fn": _command_attr(
            command_module,
            "_resolve_auth_provider_context",
        ),
        "resolve_context_auth_mode_fn": _command_attr(command_module, "_resolve_context_auth_mode"),
        "token_ref_from_auth_fn": _command_attr(command_module, "_token_ref_from_auth"),
        "auth_store_for_context_fn": _command_attr(command_module, "_auth_store_for_context"),
        "build_auth_status_lines_fn": _command_attr(command_module, "_build_auth_status_lines"),
        "status_contract_for_non_session_mode_fn": _command_attr(
            command_module,
            "_status_contract_for_non_session_mode",
        ),
        "auth_command_hint_fn": _command_attr(command_module, "_auth_command_hint"),
        "is_truthy_fn": _command_attr(command_module, "_is_truthy"),
        "safe_int_fn": _command_attr(command_module, "_safe_int"),
        "resolve_oauth_endpoints_fn": _command_attr(command_module, "_resolve_oauth_endpoints"),
        "save_session_from_oauth_result_fn": _command_attr(
            command_module,
            "_save_session_from_oauth_result",
        ),
        "refresh_daemon_handle_fn": _command_attr(command_module, "_refresh_daemon_handle"),
        "collect_refresh_contexts_fn": _command_attr(command_module, "_collect_refresh_contexts"),
        "ensure_auth_session_status_fn": _command_attr(command_module, "ensure_auth_session_status"),
        "auth_session_status_fn": _command_attr(command_module, "auth_session_status"),
        "auth_session_factory": _command_attr(command_module, "AuthSession"),
        "start_device_flow_fn": _command_attr(command_module, "start_device_flow"),
        "poll_device_flow_fn": _command_attr(command_module, "poll_device_flow"),
        "start_pkce_authorization_fn": _command_attr(command_module, "start_pkce_authorization"),
        "wait_for_pkce_callback_fn": _command_attr(command_module, "wait_for_pkce_callback"),
        "exchange_pkce_authorization_code_fn": _command_attr(
            command_module,
            "exchange_pkce_authorization_code",
        ),
        "refresh_oauth_token_fn": _command_attr(command_module, "refresh_oauth_token"),
        "refresh_due_sessions_fn": _command_attr(command_module, "refresh_due_sessions"),
        "start_refresh_daemon_fn": _command_attr(command_module, "start_refresh_daemon"),
        "stop_refresh_daemon_fn": _command_attr(command_module, "stop_refresh_daemon"),
        "refresh_daemon_status_fn": _command_attr(command_module, "refresh_daemon_status"),
        "start_managed_refresh_daemon_fn": _command_attr(
            command_module,
            "start_managed_refresh_daemon",
        ),
        "stop_managed_refresh_daemon_fn": _command_attr(command_module, "stop_managed_refresh_daemon"),
        "managed_refresh_daemon_status_fn": _command_attr(
            command_module,
            "managed_refresh_daemon_status",
        ),
    }


def handle_connect_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: Any | None = None,
    command_module: Any,
    connect_auth_modes: set[str],
    connect_write_scopes: set[str],
) -> tuple[str, list]:
    deps = _connect_command_deps(command_module)
    return provider_connect_flow_runtime.handle_connect_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        parse_connect_args_fn=deps["parse_connect_args_fn"],
        slash_invocation_inputs_fn=deps["slash_invocation_inputs_fn"],
        connect_usage_text_fn=deps["connect_usage_text_fn"],
        resolved_connect_auth_mode_fn=deps["resolved_connect_auth_mode_fn"],
        resolved_connect_api_key_env_fn=deps["resolved_connect_api_key_env_fn"],
        connect_requires_base_url_fn=deps["connect_requires_base_url_fn"],
        connect_next_action_hint_fn=deps["connect_next_action_hint_fn"],
        resolve_connect_write_path_fn=deps["resolve_connect_write_path_fn"],
        save_user_model_selection_fn=deps["save_user_model_selection_fn"],
        load_toml_document_text_fn=deps["load_toml_document_text_fn"],
        write_toml_document_text_fn=deps["write_toml_document_text_fn"],
        upsert_provider_profile_fn=deps["upsert_provider_profile_fn"],
        provider_profile_name_fn=deps["provider_profile_name_fn"],
        upsert_provider_base_url_fn=deps["upsert_provider_base_url_fn"],
        upsert_provider_auth_fields_fn=deps["upsert_provider_auth_fields_fn"],
        clear_connect_provider_fields_fn=deps["clear_connect_provider_fields_fn"],
        upsert_model_entry_fn=deps["upsert_model_entry_fn"],
        slash_command_text_fn=deps["slash_command_text_fn"],
        connect_auth_modes=connect_auth_modes,
        connect_write_scopes=connect_write_scopes,
    )


def handle_auth_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: Any | None = None,
    command_module: Any,
    auth_subcommands: set[str],
) -> tuple[str, list]:
    return provider_auth_flow_runtime.handle_auth_command(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        deps=_auth_command_deps(command_module),
        auth_subcommands=auth_subcommands,
    )


def handle_provider_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[ToolEvent]]],
    slash_invocation: Any | None = None,
    command_module: Any,
) -> tuple[str, list[ToolEvent]] | None:
    if name == "connect":
        result = _command_attr(command_module, "_handle_connect_command")(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
        )
        provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
            runtime,
            reason="connect_command",
        )
        return result
    if name == "auth":
        result = _command_attr(command_module, "_handle_auth_command")(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
        )
        provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
            runtime,
            reason="auth_command",
        )
        return result
    if name in {"chat", "reasoner"}:
        return provider_dispatch_helpers_runtime.handle_provider_line_switch_command(
            runtime,
            name=name,
            switch_disabled_result=switch_disabled_result,
        )
    if name == "providers":
        return provider_dispatch_helpers_runtime.handle_providers_command(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
        )
    if name == "models":
        return provider_dispatch_helpers_runtime.handle_models_command(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
        )
    if name == "models_refresh":
        return handle_models_refresh_command(runtime, arg_text=arg_text)
    if name == "models_cache_status":
        return handle_models_cache_status_command(runtime, arg_text=arg_text)
    if name == "provider":
        return provider_dispatch_helpers_runtime.handle_provider_selection_command(
            runtime,
            arg_text=arg_text,
            switch_disabled_result=switch_disabled_result,
            slash_invocation=slash_invocation,
        )
    if name == "model":
        return provider_dispatch_helpers_runtime.handle_model_command(
            runtime,
            arg_text=arg_text,
            switch_disabled_result=switch_disabled_result,
            slash_invocation=slash_invocation,
        )
    if name in {"model-route", "model_route"}:
        return provider_dispatch_helpers_runtime.handle_model_route_command(
            runtime,
            name=name,
            arg_text=arg_text,
            switch_disabled_result=switch_disabled_result,
            slash_invocation=slash_invocation,
        )
    if name in {"delegate-model", "delegate_model"}:
        return provider_dispatch_helpers_runtime.handle_delegate_model_command(
            runtime,
            name=name,
            arg_text=arg_text,
            switch_disabled_result=switch_disabled_result,
            slash_invocation=slash_invocation,
        )
    return None
