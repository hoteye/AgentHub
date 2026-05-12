from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_core import (
    provider_commands_dispatch_projection_helpers_runtime as provider_dispatch_projection_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_dispatch_pure_helpers_runtime as provider_dispatch_pure_helpers_runtime,
)
from cli.agent_cli.slash_parser import SlashInvocation


def handle_model_route_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[Any]]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    positionals, options, _extras = provider_dispatch_pure_helpers_runtime.model_inputs_from_source(
        runtime,
        command_name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
    )
    if len(positionals) > 2:
        return (provider_dispatch_projection_helpers_runtime.command_usage_text("model-route"), [])
    status = dict(runtime.agent.provider_status() or {})
    route_overrides = provider_dispatch_pure_helpers_runtime.session_overrides(
        runtime.agent,
        "session_route_overrides",
    )
    if not positionals:
        return (
            provider_dispatch_projection_helpers_runtime.route_overview_text(
                status,
                route_overrides=route_overrides,
            ),
            [],
        )
    route_name = positionals[0]
    selector = positionals[1] if len(positionals) > 1 else None
    provider_name = str(options.get("provider") or "").strip() or None
    reasoning_effort = str(options.get("reasoning-effort") or "").strip() or None
    timeout_text = str(options.get("timeout") or "").strip() or None
    clear = bool(options.get("clear"))
    if (
        selector is None
        and provider_name is None
        and reasoning_effort is None
        and timeout_text is None
        and not clear
    ):
        route_key = f"route_{route_name}"
        route_status = str(status.get(route_key) or "").strip()
        if not route_status:
            return (f"unknown or unavailable route: {route_name}", [])
        override_active = (
            "true"
            if isinstance(route_overrides, dict) and route_name in route_overrides
            else "false"
        )
        return (
            provider_dispatch_projection_helpers_runtime.route_current_text(
                route_name=route_name,
                route_status=route_status,
                override_active=override_active,
            ),
            [],
        )
    try:
        status = runtime.configure_route_selection(
            route_name,
            model=selector,
            provider=provider_name,
            reasoning_effort=reasoning_effort,
            timeout=timeout_text,
            clear=clear,
        )
    except RuntimeError as exc:
        return switch_disabled_result(exc)
    except ValueError as exc:
        return (str(exc), [])
    route_status = str(status.get(f"route_{route_name}") or "-")
    return (
        provider_dispatch_projection_helpers_runtime.route_update_text(
            route_name=route_name,
            route_status=route_status,
            clear=clear,
        ),
        [],
    )


def handle_delegate_model_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[Any]]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    positionals, options, _extras = provider_dispatch_pure_helpers_runtime.model_inputs_from_source(
        runtime,
        command_name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
    )
    if len(positionals) > 2:
        return (
            provider_dispatch_projection_helpers_runtime.command_usage_text("delegate-model"),
            [],
        )
    status = dict(runtime.agent.provider_status() or {})
    delegate_overrides = provider_dispatch_pure_helpers_runtime.session_overrides(
        runtime.agent,
        "session_delegate_overrides",
    )
    if not positionals:
        return (
            provider_dispatch_projection_helpers_runtime.delegate_overview_text(
                status,
                delegate_overrides=delegate_overrides,
            ),
            [],
        )
    role_name = positionals[0]
    selector = positionals[1] if len(positionals) > 1 else None
    provider_name = str(options.get("provider") or "").strip() or None
    reasoning_effort = str(options.get("reasoning-effort") or "").strip() or None
    timeout_text = str(options.get("timeout") or "").strip() or None
    clear = bool(options.get("clear"))
    if (
        selector is None
        and provider_name is None
        and reasoning_effort is None
        and timeout_text is None
        and not clear
    ):
        delegate_key = f"delegate_{role_name}"
        delegate_status = str(status.get(delegate_key) or "").strip()
        if not delegate_status:
            return (f"unknown or unavailable delegation role: {role_name}", [])
        override_active = (
            "true"
            if isinstance(delegate_overrides, dict) and role_name in delegate_overrides
            else "false"
        )
        return (
            provider_dispatch_projection_helpers_runtime.delegate_current_text(
                role_name=role_name,
                delegate_status=delegate_status,
                override_active=override_active,
            ),
            [],
        )
    try:
        status = runtime.configure_delegate_selection(
            role_name,
            model=selector,
            provider=provider_name,
            reasoning_effort=reasoning_effort,
            timeout=timeout_text,
            clear=clear,
        )
    except RuntimeError as exc:
        return switch_disabled_result(exc)
    except ValueError as exc:
        return (str(exc), [])
    delegate_status = str(status.get(f"delegate_{role_name}") or "-")
    return (
        provider_dispatch_projection_helpers_runtime.delegate_update_text(
            role_name=role_name,
            delegate_status=delegate_status,
            clear=clear,
        ),
        [],
    )


__all__ = [
    "handle_delegate_model_command",
    "handle_model_route_command",
]
