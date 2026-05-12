from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core import (
    provider_commands_projection_helpers_runtime as provider_projection_helpers_runtime,
)
from cli.agent_cli.slash_surface import surface_usage_text


def provider_usage_text() -> str:
    return provider_projection_helpers_runtime.provider_usage_text(
        surface_usage_text_fn=surface_usage_text,
    )


def model_usage_text() -> str:
    return provider_projection_helpers_runtime.model_usage_text(
        surface_usage_text_fn=surface_usage_text,
    )


def command_usage_text(command_name: str) -> str:
    return f"Usage: {surface_usage_text(command_name)}"


def providers_command_text(
    providers: list[dict[str, Any]],
    *,
    probe_requested: bool,
) -> str:
    lines = [f"providers={len(providers)}"]
    for item in providers:
        base = f"- {item['provider_name']}: default_model={item['default_model']}"
        if not probe_requested:
            lines.append(base)
            continue
        probe_status = str(item.get("probe_status") or "").strip() or "unknown"
        suffix = [f"probe={probe_status}"]
        probe_latency_ms = item.get("probe_latency_ms")
        if probe_latency_ms not in (None, "", 0):
            suffix.append(f"latency_ms={probe_latency_ms}")
        probe_failure_code = str(item.get("probe_failure_code") or "").strip()
        if probe_failure_code:
            suffix.append(f"failure_code={probe_failure_code}")
        lines.append(f"{base}, {', '.join(suffix)}")
    return "\n".join(lines)


def models_command_text(models: list[dict[str, Any]]) -> str:
    lines = [f"models={len(models)}"]
    for item in models:
        model_key = str(item.get("model_key") or "-").strip() or "-"
        display_name = str(item.get("display_name") or item.get("model_id") or "").strip()
        if display_name and display_name != model_key:
            lines.append(f"- {model_key}: {display_name}")
        else:
            lines.append(f"- {model_key}")
    return "\n".join(lines)


def provider_switch_text(
    status: dict[str, Any],
    *,
    provider_name: str,
    write_scope: str,
    write_path: str,
    probe_payload: dict[str, Any] | None = None,
) -> str:
    provider_ready = str(status.get("provider_ready") or "false")
    provider_public = str(status.get("provider_public_name") or provider_name or "").strip()
    headline = provider_projection_helpers_runtime.provider_switch_headline(
        provider_public=provider_public,
        provider_name=provider_name,
        provider_ready=provider_ready,
        write_scope=write_scope,
    )
    lines = provider_projection_helpers_runtime.provider_summary_lines(dict(status or {}))[1:]
    lines.append(f"write_scope={write_scope}")
    if write_path:
        lines.append(f"write_path={write_path}")
    if probe_payload:
        lines.extend(provider_projection_helpers_runtime.provider_probe_lines(dict(probe_payload or {})))
    return "\n".join([headline, *lines])


def provider_status_text(
    status: dict[str, Any],
    *,
    verbose: bool,
    probe_payload: dict[str, Any] | None = None,
    route_summary: str = "",
    delegate_summary: str = "",
    runtime_summary: str = "",
    provider_readiness_summary: str = "",
    route_health_summary: str = "",
    reason_surface: str = "",
    budget_surface: str = "",
) -> str:
    lines = provider_projection_helpers_runtime.provider_summary_lines(dict(status or {}))
    if probe_payload:
        lines.extend(provider_projection_helpers_runtime.provider_probe_lines(dict(probe_payload or {})))
    if not verbose:
        return "\n".join(lines)
    lines.extend(
        provider_projection_helpers_runtime.provider_verbose_lines(
            dict(status or {}),
            route_summary=route_summary,
            delegate_summary=delegate_summary,
            runtime_summary=runtime_summary,
            provider_readiness_summary=provider_readiness_summary,
            route_health_summary=route_health_summary,
            reason_surface=reason_surface,
            budget_surface=budget_surface,
        )
    )
    return "\n".join(lines)


def model_status_text(status: dict[str, Any]) -> str:
    return "\n".join(provider_projection_helpers_runtime.model_status_lines(dict(status or {})))


def model_selection_text(
    status: dict[str, Any],
    *,
    model_selector: str | None,
    reasoning_effort: str | None,
    write_scope: str,
    write_path: str,
) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.model_selection_lines(
            dict(status or {}),
            model_selector=model_selector,
            reasoning_effort=reasoning_effort,
            write_scope=write_scope,
            write_path=write_path,
        )
    )


def route_overview_text(status: dict[str, Any], *, route_overrides: Any) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.route_overview_lines(
            dict(status or {}),
            route_overrides=route_overrides,
        )
    )


def route_current_text(
    *,
    route_name: str,
    route_status: str,
    override_active: str,
) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.route_current_lines(
            route_name=route_name,
            route_status=route_status,
            override_active=override_active,
        )
    )


def route_update_text(
    *,
    route_name: str,
    route_status: str,
    clear: bool,
) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.route_update_lines(
            route_name=route_name,
            route_status=route_status,
            clear=clear,
        )
    )


def delegate_overview_text(status: dict[str, Any], *, delegate_overrides: Any) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.delegate_overview_lines(
            dict(status or {}),
            delegate_overrides=delegate_overrides,
        )
    )


def delegate_current_text(
    *,
    role_name: str,
    delegate_status: str,
    override_active: str,
) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.delegate_current_lines(
            role_name=role_name,
            delegate_status=delegate_status,
            override_active=override_active,
        )
    )


def delegate_update_text(
    *,
    role_name: str,
    delegate_status: str,
    clear: bool,
) -> str:
    return "\n".join(
        provider_projection_helpers_runtime.delegate_update_lines(
            role_name=role_name,
            delegate_status=delegate_status,
            clear=clear,
        )
    )


__all__ = [
    "command_usage_text",
    "delegate_current_text",
    "delegate_overview_text",
    "delegate_update_text",
    "model_selection_text",
    "model_status_text",
    "model_usage_text",
    "models_command_text",
    "provider_status_text",
    "provider_switch_text",
    "provider_usage_text",
    "providers_command_text",
    "route_current_text",
    "route_overview_text",
    "route_update_text",
]
