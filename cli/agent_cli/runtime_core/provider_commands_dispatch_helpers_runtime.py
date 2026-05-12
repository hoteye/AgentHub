from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_core import (
    provider_commands_dispatch_projection_helpers_runtime as provider_dispatch_projection_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_dispatch_pure_helpers_runtime as provider_dispatch_pure_helpers_runtime,
)
from cli.agent_cli.runtime_core.provider_commands_dispatch_route_delegate_runtime import (
    handle_delegate_model_command,
    handle_model_route_command,
)
from cli.agent_cli.runtime_core.provider_commands_helpers import (
    _orchestration_budget_surface,
    _orchestration_delegate_summary,
    _orchestration_reason_surface,
    _orchestration_route_summary,
    _orchestration_runtime_summary,
    _provider_readiness_summary,
    _route_health_summary,
)
from cli.agent_cli.runtime_kernels.routing import sidecar_provider_hint_lines
from cli.agent_cli.runtime_services import (
    provider_availability_refresh_runtime as provider_availability_refresh_runtime_service,
)
from cli.agent_cli.slash_parser import SlashInvocation


def handle_provider_line_switch_command(
    runtime: Any,
    *,
    name: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[Any]]],
) -> tuple[str, list[Any]]:
    try:
        status = runtime.agent.switch_provider_line(name)
    except RuntimeError as exc:
        return switch_disabled_result(exc)
    provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
        runtime,
        reason="provider_selection_change",
    )
    provider_label = str(status.get("provider_label") or "-")
    provider_planner = str(status.get("provider_planner") or "-")
    provider_source = str(status.get("provider_source") or "-")
    return (
        f"switched session provider to {name}\n"
        f"provider_label={provider_label}\n"
        f"provider_planner={provider_planner}\n"
        f"provider_source={provider_source}",
        [],
    )


def handle_providers_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
        runtime,
        reason="providers_command",
    )
    slash_inputs = provider_dispatch_pure_helpers_runtime.slash_invocation_inputs(slash_invocation)
    if slash_inputs is not None:
        _raw_tokens, _positionals, options, _extras = slash_inputs
    else:
        _, options = runtime._parse_args(arg_text)
    probe_requested = bool(options.get("probe"))
    if probe_requested:
        providers = runtime.agent.probe_providers(writeback_availability=True)
    else:
        providers = runtime.agent.available_providers()
    return (
        provider_dispatch_projection_helpers_runtime.providers_command_text(
            list(providers or []),
            probe_requested=probe_requested,
        ),
        [],
    )


def handle_models_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    if slash_invocation is not None:
        provider_filter = (
            str(slash_invocation.positionals[0] if slash_invocation.positionals else "").strip()
            or None
        )
    else:
        provider_filter = arg_text.strip() or None
    models = provider_dispatch_pure_helpers_runtime.available_models_with_fallback(
        runtime,
        provider_filter,
    )
    return (provider_dispatch_projection_helpers_runtime.models_command_text(models), [])


def handle_provider_selection_command(
    runtime: Any,
    *,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[Any]]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
        runtime,
        reason="provider_command",
    )
    slash_inputs = provider_dispatch_pure_helpers_runtime.slash_invocation_inputs(slash_invocation)
    selection_inputs = provider_dispatch_pure_helpers_runtime.parse_provider_selection_inputs(
        arg_text,
        slash_inputs=slash_inputs,
    )
    raw_tokens = list(selection_inputs["raw_tokens"])
    provider_positionals = list(selection_inputs["provider_positionals"])
    verbose = bool(selection_inputs["verbose"])
    probe_requested = bool(selection_inputs["probe_requested"])
    write_scope = str(selection_inputs["write_scope"] or "user")
    if len(provider_positionals) > 1:
        return (provider_dispatch_projection_helpers_runtime.provider_usage_text(), [])
    if write_scope not in provider_dispatch_pure_helpers_runtime.selection_write_scopes():
        return (
            f"{provider_dispatch_projection_helpers_runtime.provider_usage_text()}\n"
            f"invalid_write_scope={write_scope or '-'}",
            [],
        )
    if selection_inputs["missing_write_value"] or (
        not provider_positionals
        and any(str(token or "").strip() == "--write" for token in raw_tokens)
    ):
        return (provider_dispatch_projection_helpers_runtime.provider_usage_text(), [])

    if provider_positionals:
        provider_name = provider_positionals[0]
        if provider_name.startswith("-"):
            return (provider_dispatch_projection_helpers_runtime.provider_usage_text(), [])
        try:
            status = provider_dispatch_pure_helpers_runtime.switch_provider_with_fallback(
                runtime,
                provider_name,
                write_scope=write_scope,
            )
        except RuntimeError as exc:
            return switch_disabled_result(exc)
        provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh(
            runtime,
            reason="provider_selection_change",
        )
        probe_payload = (
            dict(runtime.agent.probe_provider(writeback_availability=True) or {})
            if probe_requested
            else None
        )
        status_payload = dict(status or {})
        write_path = provider_dispatch_pure_helpers_runtime.selection_write_path(
            status_payload,
            write_scope=write_scope,
        )
        return (
            provider_dispatch_projection_helpers_runtime.provider_switch_text(
                status_payload,
                provider_name=provider_name,
                write_scope=write_scope,
                write_path=write_path,
                probe_payload=probe_payload,
            ),
            [],
        )

    status = dict(runtime.agent.provider_status() or {})
    sidecar_hints = sidecar_provider_hint_lines(status)
    probe_payload = (
        dict(runtime.agent.probe_provider(writeback_availability=True) or {})
        if probe_requested
        else None
    )
    route_summary = _orchestration_route_summary(status)
    delegate_summary = _orchestration_delegate_summary(status)
    runtime_summary = _orchestration_runtime_summary(status)
    provider_readiness_summary = _provider_readiness_summary(status)
    route_health_summary = _route_health_summary(status)
    reason_surface = _orchestration_reason_surface(status)
    budget_surface = _orchestration_budget_surface(status)
    rendered = (
        provider_dispatch_projection_helpers_runtime.provider_status_text(
            status,
            verbose=verbose,
            probe_payload=probe_payload,
            route_summary=route_summary,
            delegate_summary=delegate_summary,
            runtime_summary=runtime_summary,
            provider_readiness_summary=provider_readiness_summary,
            route_health_summary=route_health_summary,
            reason_surface=reason_surface,
            budget_surface=budget_surface,
        )
        if verbose
        else provider_dispatch_projection_helpers_runtime.provider_status_text(
            status,
            verbose=False,
            probe_payload=probe_payload,
        )
    )
    if sidecar_hints:
        rendered = "\n".join([rendered, *sidecar_hints])
    return (rendered, [])


def handle_model_command(
    runtime: Any,
    *,
    arg_text: str,
    switch_disabled_result: Callable[[Exception], tuple[str, list[Any]]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    positionals, options, extras = provider_dispatch_pure_helpers_runtime.model_inputs_from_source(
        runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
    )
    reasoning_effort = str(options.get("reasoning-effort") or "").strip() or None
    try:
        write_scope = provider_dispatch_pure_helpers_runtime.normalized_selection_write_scope(
            options.get("write"),
            default="user",
        )
    except ValueError as exc:
        return (
            f"{provider_dispatch_projection_helpers_runtime.model_usage_text()}\n"
            f"invalid_write_scope={exc}",
            [],
        )
    model_selector = positionals[0] if positionals else None
    if len(positionals) > 1:
        return (provider_dispatch_projection_helpers_runtime.model_usage_text(), [])
    if not positionals and provider_dispatch_pure_helpers_runtime.extras_include_any(
        extras,
        {"--write", "write", "--reasoning-effort", "reasoning-effort"},
    ):
        return (provider_dispatch_projection_helpers_runtime.model_usage_text(), [])
    if model_selector is None and reasoning_effort is None:
        if "write" in options:
            return (provider_dispatch_projection_helpers_runtime.model_usage_text(), [])
        status = runtime.agent.provider_status()
        return (
            provider_dispatch_projection_helpers_runtime.model_status_text(dict(status or {})),
            [],
        )
    try:
        status = provider_dispatch_pure_helpers_runtime.configure_model_selection_with_fallback(
            runtime,
            model_selector=model_selector,
            reasoning_effort=reasoning_effort,
            write_scope=write_scope,
        )
    except RuntimeError as exc:
        return switch_disabled_result(exc)
    except ValueError as exc:
        return (str(exc), [])
    return (
        provider_dispatch_projection_helpers_runtime.model_selection_text(
            dict(status or {}),
            model_selector=model_selector,
            reasoning_effort=reasoning_effort,
            write_scope=write_scope,
            write_path=provider_dispatch_pure_helpers_runtime.selection_write_path(
                dict(status or {}),
                write_scope=write_scope,
            ),
        ),
        [],
    )


__all__ = [
    "handle_delegate_model_command",
    "handle_model_command",
    "handle_model_route_command",
    "handle_models_command",
    "handle_provider_line_switch_command",
    "handle_provider_selection_command",
    "handle_providers_command",
]
