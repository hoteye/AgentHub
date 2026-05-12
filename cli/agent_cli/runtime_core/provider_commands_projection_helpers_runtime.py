from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import (
    provider_commands_projection_route_delegate_helpers_runtime as _route_delegate_helpers,
    provider_commands_projection_status_helpers_runtime as _status_helpers,
    provider_commands_projection_usage_auth_helpers_runtime as _usage_auth_helpers,
)


def provider_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return _usage_auth_helpers.provider_usage_text(
        surface_usage_text_fn=surface_usage_text_fn,
    )


def model_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return _usage_auth_helpers.model_usage_text(
        surface_usage_text_fn=surface_usage_text_fn,
    )


def connect_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return _usage_auth_helpers.connect_usage_text(
        surface_usage_text_fn=surface_usage_text_fn,
    )


def auth_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return _usage_auth_helpers.auth_usage_text(
        surface_usage_text_fn=surface_usage_text_fn,
    )


def slash_command_text(name: str, *parts: str) -> str:
    return _usage_auth_helpers.slash_command_text(name, *parts)


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
    return _usage_auth_helpers.auth_command_hint(
        action,
        provider_name=provider_name,
        mode=mode,
        poll=poll,
        auth_code=auth_code,
        state=state,
        auto=auto,
        daemon=daemon,
        managed=managed,
        slash_command_text_fn=slash_command_text,
    )


def build_auth_status_lines(
    *,
    subcommand: str,
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    next_action: str,
) -> list[str]:
    return _usage_auth_helpers.build_auth_status_lines(
        subcommand=subcommand,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=next_action,
    )


def provider_summary_lines(status_payload: dict[str, Any]) -> list[str]:
    return _status_helpers.provider_summary_lines(status_payload)


def provider_probe_lines(probe_payload: dict[str, Any]) -> list[str]:
    return _status_helpers.provider_probe_lines(probe_payload)


def provider_switch_headline(
    *,
    provider_public: str,
    provider_name: str,
    provider_ready: str,
    write_scope: str,
) -> str:
    return _status_helpers.provider_switch_headline(
        provider_public=provider_public,
        provider_name=provider_name,
        provider_ready=provider_ready,
        write_scope=write_scope,
    )


def provider_verbose_lines(
    status: dict[str, Any],
    *,
    route_summary: str,
    delegate_summary: str,
    runtime_summary: str,
    provider_readiness_summary: str,
    route_health_summary: str,
    reason_surface: str,
    budget_surface: str,
) -> list[str]:
    return _status_helpers.provider_verbose_lines(
        status,
        route_summary=route_summary,
        delegate_summary=delegate_summary,
        runtime_summary=runtime_summary,
        provider_readiness_summary=provider_readiness_summary,
        route_health_summary=route_health_summary,
        reason_surface=reason_surface,
        budget_surface=budget_surface,
    )


def model_status_lines(status: dict[str, Any]) -> list[str]:
    return _status_helpers.model_status_lines(status)


def model_selection_lines(
    status: dict[str, Any],
    *,
    model_selector: str | None,
    reasoning_effort: str | None,
    write_scope: str,
    write_path: str,
) -> list[str]:
    return _status_helpers.model_selection_lines(
        status,
        model_selector=model_selector,
        reasoning_effort=reasoning_effort,
        write_scope=write_scope,
        write_path=write_path,
    )


def route_overview_lines(status: dict[str, Any], *, route_overrides: Any) -> list[str]:
    return _route_delegate_helpers.route_overview_lines(
        status,
        route_overrides=route_overrides,
    )


def route_current_lines(
    *,
    route_name: str,
    route_status: str,
    override_active: str,
) -> list[str]:
    return _route_delegate_helpers.route_current_lines(
        route_name=route_name,
        route_status=route_status,
        override_active=override_active,
    )


def route_update_lines(
    *,
    route_name: str,
    route_status: str,
    clear: bool,
) -> list[str]:
    return _route_delegate_helpers.route_update_lines(
        route_name=route_name,
        route_status=route_status,
        clear=clear,
    )


def delegate_overview_lines(status: dict[str, Any], *, delegate_overrides: Any) -> list[str]:
    return _route_delegate_helpers.delegate_overview_lines(
        status,
        delegate_overrides=delegate_overrides,
    )


def delegate_current_lines(
    *,
    role_name: str,
    delegate_status: str,
    override_active: str,
) -> list[str]:
    return _route_delegate_helpers.delegate_current_lines(
        role_name=role_name,
        delegate_status=delegate_status,
        override_active=override_active,
    )


def delegate_update_lines(
    *,
    role_name: str,
    delegate_status: str,
    clear: bool,
) -> list[str]:
    return _route_delegate_helpers.delegate_update_lines(
        role_name=role_name,
        delegate_status=delegate_status,
        clear=clear,
    )


__all__ = [
    "auth_command_hint",
    "auth_usage_text",
    "build_auth_status_lines",
    "connect_usage_text",
    "delegate_current_lines",
    "delegate_overview_lines",
    "delegate_update_lines",
    "model_selection_lines",
    "model_status_lines",
    "model_usage_text",
    "provider_probe_lines",
    "provider_summary_lines",
    "provider_switch_headline",
    "provider_usage_text",
    "provider_verbose_lines",
    "route_current_lines",
    "route_overview_lines",
    "route_update_lines",
    "slash_command_text",
]
