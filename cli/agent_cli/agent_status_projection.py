from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any


def _session_line(*, provider_planner: str, provider_public_name: str) -> str:
    if provider_planner == "deepseek_reasoner":
        return "reasoner"
    if provider_public_name == "deepseek":
        return "chat-tools"
    return f"{provider_public_name}-tools"


def build_ready_provider_status(
    summary: Mapping[str, Any],
    *,
    config_path: str,
    auth_path: str,
    selection_path: str,
    host_platform: Any,
    public_provider_name_fn: Callable[..., str],
) -> dict[str, str]:
    provider_name = str(summary.get("provider_name") or "-")
    model_key = str(summary.get("model_key") or "-")
    provider_model = str(summary.get("model") or "-")
    provider_planner = str(summary.get("planner_kind") or "-")
    provider_public_name = (
        public_provider_name_fn(
            provider_name=provider_name,
            model=provider_model,
            base_url=str(summary.get("base_url") or ""),
            planner_kind=provider_planner,
        )
        or provider_name
    )
    provider_tools = "tool-calls"
    session_line = _session_line(
        provider_planner=provider_planner,
        provider_public_name=provider_public_name,
    )
    shell_program = str(
        host_platform.resolve_shell_program(None) or host_platform.shell_program or "-"
    )
    return {
        "provider_ready": "true",
        "provider_name": provider_name,
        "provider_public_name": provider_public_name,
        "provider_route_name": provider_name,
        "model_key": model_key,
        "provider_planner": provider_planner,
        "provider_model": provider_model,
        "provider_reasoning_effort": str(summary.get("reasoning_effort") or "-") or "-",
        "provider_tools": provider_tools,
        "session_line": session_line,
        "provider_label": f"{provider_name} | {provider_model} | {provider_tools}",
        "provider_display_label": f"{provider_public_name} | {provider_model} | {provider_tools}",
        "provider_base_url": str(summary.get("base_url") or "-"),
        "provider_source": str(summary.get("source") or "-"),
        "model_raw_context_window": str(summary.get("model_raw_context_window") or "-"),
        "model_context_window": str(summary.get("model_context_window") or "-"),
        "model_auto_compact_token_limit": str(summary.get("model_auto_compact_token_limit") or "-"),
        "auth_mode": str(summary.get("auth_mode") or "-"),
        "auth_status": str(summary.get("auth_status") or "-"),
        "token_source": str(summary.get("token_source") or "-"),
        "no_auth_guardrail_reason": str(summary.get("no_auth_guardrail_reason") or "-"),
        "no_auth_guardrail_pass": str(summary.get("no_auth_guardrail_pass") or "false"),
        "provider_config_path": str(summary.get("config_path") or config_path),
        "provider_auth_path": str(summary.get("auth_path") or auth_path),
        "provider_selection_path": str(selection_path or ""),
        "platform_family": host_platform.family,
        "platform_os": host_platform.os,
        "shell_kind": host_platform.shell_kind,
        "shell_program": shell_program,
    }


def build_pending_provider_status(
    session_provider_env_overrides: Mapping[str, Any],
    *,
    planner_error: str | None,
    config_path: str,
    auth_path: str,
    selection_path: str,
    host_platform: Any,
    public_provider_name_fn: Callable[..., str],
) -> dict[str, str]:
    pending_provider_name = (
        str(session_provider_env_overrides.get("AGENT_CLI_PROVIDER") or "-") or "-"
    )
    pending_public_name = (
        public_provider_name_fn(provider_name=pending_provider_name) or pending_provider_name
    )
    shell_program = str(
        host_platform.resolve_shell_program(None) or host_platform.shell_program or "-"
    )
    return {
        "provider_ready": "false",
        "provider_name": pending_provider_name,
        "provider_public_name": pending_public_name,
        "provider_route_name": pending_provider_name,
        "model_key": "-",
        "provider_planner": "-",
        "provider_model": "-",
        "provider_reasoning_effort": str(
            session_provider_env_overrides.get("AGENT_CLI_REASONING_EFFORT") or "-"
        )
        or "-",
        "provider_tools": "-",
        "session_line": "-",
        "provider_label": f"{pending_provider_name} | - | -",
        "provider_display_label": f"{pending_public_name} | - | -",
        "provider_base_url": "-",
        "provider_source": planner_error or "not_configured",
        "auth_mode": str(session_provider_env_overrides.get("AGENT_CLI_AUTH_MODE") or "-") or "-",
        "auth_status": "-",
        "token_source": "-",
        "no_auth_guardrail_reason": "-",
        "no_auth_guardrail_pass": "false",
        "provider_config_path": config_path,
        "provider_auth_path": auth_path,
        "provider_selection_path": str(selection_path or ""),
        "platform_family": host_platform.family,
        "platform_os": host_platform.os,
        "shell_kind": host_platform.shell_kind,
        "shell_program": shell_program,
    }


def append_route_and_delegate_resolution_labels(
    status: MutableMapping[str, str],
    summary: Mapping[str, Any],
    *,
    route_names: tuple[str, ...],
    delegation_names: tuple[str, ...],
    resolution_status_label_fn: Callable[[dict[str, Any]], str],
) -> None:
    routes = summary.get("routes")
    if isinstance(routes, dict):
        for route_name in route_names:
            route_summary = routes.get(route_name)
            if isinstance(route_summary, dict):
                status[f"route_{route_name}"] = resolution_status_label_fn(route_summary)
    delegation = summary.get("delegation")
    if isinstance(delegation, dict):
        for role_name in delegation_names:
            delegation_summary = delegation.get(role_name)
            if isinstance(delegation_summary, dict):
                status[f"delegate_{role_name}"] = resolution_status_label_fn(delegation_summary)


def append_override_counts(
    status: MutableMapping[str, str],
    *,
    route_overrides: Mapping[str, Any],
    delegation_overrides: Mapping[str, Any],
) -> None:
    if route_overrides:
        status["route_override_count"] = str(len(route_overrides))
    if delegation_overrides:
        status["delegate_override_count"] = str(len(delegation_overrides))


def append_runtime_state(
    status: MutableMapping[str, str],
    *,
    runtime_error: str | None,
    diagnostic_lines: list[str],
) -> None:
    if runtime_error:
        status["provider_runtime_state"] = "degraded"
        status["provider_last_error"] = runtime_error
        if diagnostic_lines:
            status["provider_last_error_diagnostics"] = " || ".join(
                diagnostic_lines[1:] or diagnostic_lines
            )
        return
    status["provider_runtime_state"] = "ready"
