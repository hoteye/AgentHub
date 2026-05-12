from __future__ import annotations

from typing import Any


def _boolish_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def provider_summary_lines(status_payload: dict[str, Any]) -> list[str]:
    lines = ["provider status"]
    provider_public = str(
        status_payload.get("provider_public_name")
        or status_payload.get("provider_name")
        or ""
    ).strip()
    if provider_public:
        lines.append(f"provider_name={provider_public}")
    provider_model = str(status_payload.get("provider_model") or "").strip()
    if provider_model:
        lines.append(f"provider_model={provider_model}")
    provider_reasoning_effort = str(status_payload.get("provider_reasoning_effort") or "").strip()
    if provider_reasoning_effort:
        lines.append(f"provider_reasoning_effort={provider_reasoning_effort}")
    provider_ready = str(status_payload.get("provider_ready") or "").strip()
    if provider_ready:
        lines.append(f"provider_ready={provider_ready}")
    provider_source = str(status_payload.get("provider_source") or "").strip()
    if provider_source:
        lines.append(f"provider_source={provider_source}")
    provider_selection_scope = str(status_payload.get("provider_selection_scope") or "").strip()
    if _boolish_true(status_payload.get("provider_selection_active")) and provider_selection_scope:
        lines.append(f"provider_selection_scope={provider_selection_scope}")
    return lines


def provider_probe_lines(probe_payload: dict[str, Any]) -> list[str]:
    lines = [f"probe_status={str(probe_payload.get('probe_status') or '').strip() or 'unknown'}"]
    lines.append(f"probe_transport={str(probe_payload.get('probe_transport') or '').strip() or 'real_provider_send'}")
    lines.append(
        f"probe_stream_mode={str(probe_payload.get('probe_stream_mode') or '').strip() or 'noop_turn_event_callback'}"
    )
    probe_latency_ms = probe_payload.get("probe_latency_ms")
    if probe_latency_ms not in (None, ""):
        lines.append(f"probe_latency_ms={probe_latency_ms}")
    probe_failure_code = str(probe_payload.get("probe_failure_code") or "").strip()
    if probe_failure_code:
        lines.append(f"probe_failure_code={probe_failure_code}")
    probe_failure_reason = str(probe_payload.get("probe_failure_reason") or "").strip()
    if probe_failure_reason:
        lines.append(f"probe_failure_reason={probe_failure_reason}")
    probe_response_preview = str(probe_payload.get("probe_response_preview") or "").strip()
    if probe_response_preview:
        lines.append(f"probe_response_preview={probe_response_preview}")
    return lines


def provider_switch_headline(
    *,
    provider_public: str,
    provider_name: str,
    provider_ready: str,
    write_scope: str,
) -> str:
    display_name = provider_public or provider_name
    if write_scope == "session":
        return (
            f"switched provider for this session to {display_name}"
            if provider_ready == "true"
            else f"selected provider {display_name} for this session, but it is not configured"
        )
    if write_scope == "project":
        return (
            f"switched provider to {display_name} and saved in workspace config"
            if provider_ready == "true"
            else f"selected provider {display_name} in workspace config, but it is not configured"
        )
    return (
        f"switched provider to {display_name} and saved as user default"
        if provider_ready == "true"
        else f"selected provider {display_name} as user default, but it is not configured"
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
    lines: list[str] = []
    rendered_keys: set[str] = {
        "provider_name",
        "provider_public_name",
        "provider_model",
        "provider_reasoning_effort",
        "provider_ready",
        "provider_source",
    }

    def append_status_value(key: str, *, include_dash: bool = False) -> None:
        raw_value = status.get(key)
        text = str(raw_value or "").strip()
        if not text:
            return
        if text == "-" and not include_dash:
            return
        lines.append(f"{key}={raw_value}")
        rendered_keys.add(key)

    def append_status_alias(key: str, *fallback_keys: str, include_dash: bool = False) -> None:
        for candidate in (key, *fallback_keys):
            raw_value = status.get(candidate)
            text = str(raw_value or "").strip()
            if not text:
                continue
            if text == "-" and not include_dash:
                continue
            lines.append(f"{key}={raw_value}")
            rendered_keys.add(candidate)
            if candidate == key:
                rendered_keys.add(key)
            return

    provider_label = str(status.get("provider_display_label") or status.get("provider_label") or "").strip()
    if provider_label:
        lines.append(f"provider_label={provider_label}")
        rendered_keys.add("provider_display_label")
        rendered_keys.add("provider_label")
    provider_route = str(status.get("provider_route_name") or "").strip()
    provider_public = str(status.get("provider_public_name") or status.get("provider_name") or "").strip()
    if provider_route and provider_route not in {"-", provider_public}:
        lines.append(f"provider_route={provider_route}")
        rendered_keys.add("provider_route_name")
    append_status_value("provider_planner")
    append_status_value("provider_tools")
    append_status_value("session_line")
    append_status_value("auth_mode")
    append_status_value("auth_status")
    append_status_value("token_source")
    append_status_value("no_auth_guardrail_reason")
    append_status_value("no_auth_guardrail_pass")
    append_status_value("provider_runtime_state")
    append_status_value("provider_last_error")
    append_status_value("provider_last_error_diagnostics")
    if route_summary:
        lines.append(f"delegation_route_summary={route_summary}")
    if delegate_summary:
        lines.append(f"delegation_delegate_summary={delegate_summary}")
    if provider_readiness_summary:
        lines.append(f"provider_readiness_summary={provider_readiness_summary}")
    if route_health_summary:
        lines.append(f"route_health_summary={route_health_summary}")
    if runtime_summary:
        lines.append(f"delegation_runtime_summary={runtime_summary}")
    if reason_surface:
        lines.append(f"delegation_reason_surface={reason_surface}")
    if budget_surface:
        lines.append(f"delegation_budget_surface={budget_surface}")
    append_status_alias("delegation_stay_local_source", "orchestration_stay_local_source")
    append_status_alias("delegation_stay_local_reason", "orchestration_stay_local_reason")
    append_status_alias(
        "delegation_stay_local_counterexamples",
        "orchestration_stay_local_counterexamples",
    )
    append_status_value("observed_tool_count")
    append_status_value("observed_delegation_tool_count")
    append_status_value("observed_non_delegation_tool_count")
    append_status_value("route_policy_helper")
    append_status_value("route_tool_followup")
    append_status_value("route_final_synthesis")
    append_status_value("delegate_subagent")
    append_status_value("delegate_teammate")
    append_status_value("route_override_count")
    append_status_value("delegate_override_count")
    append_status_value("provider_config_path")
    append_status_value("provider_auth_path")
    append_status_value("provider_selection_path")
    append_status_value("provider_source_raw")
    append_status_value("provider_config_scope")
    append_status_value("provider_selection_scope")
    append_status_value("provider_selection_active")
    append_status_value("provider_runtime_home_active")
    append_status_value("provider_runtime_home_path")
    append_status_value("platform_family")
    append_status_value("platform_os")
    append_status_value("shell_kind")
    append_status_value("shell_program")
    lines.append("provider_verbose=true")
    for key, value in status.items():
        if key in rendered_keys:
            continue
        lines.append(f"{key}={value}")
    return lines


def model_status_lines(status: dict[str, Any]) -> list[str]:
    return [
        f"current_model={status.get('provider_model')}",
        f"model_key={status.get('model_key') or '-'}",
        f"current_reasoning_effort={status.get('provider_reasoning_effort') or '-'}",
        f"session_line={status.get('session_line') or '-'}",
    ]


def model_selection_lines(
    status: dict[str, Any],
    *,
    model_selector: str | None,
    reasoning_effort: str | None,
    write_scope: str,
    write_path: str,
) -> list[str]:
    provider_label = str(status.get("provider_display_label") or status.get("provider_label") or "-")
    provider_planner = str(status.get("provider_planner") or "-")
    provider_source = str(status.get("provider_source") or "-")
    provider_ready = str(status.get("provider_ready") or "false")
    current_reasoning_effort = str(status.get("provider_reasoning_effort") or "-")
    change_bits: list[str] = []
    if model_selector is not None:
        change_bits.append(f"model={model_selector}")
    if reasoning_effort is not None:
        change_bits.append(f"reasoning_effort={reasoning_effort}")
    change_summary = ", ".join(change_bits) or "model selection"
    scope_label = {
        "session": "session",
        "user": "user default",
        "project": "workspace default",
    }[write_scope]
    headline = (
        f"updated {scope_label} {change_summary}"
        if provider_ready == "true"
        else f"selected {scope_label} {change_summary}, but it is not configured"
    )
    lines = [
        headline,
        f"provider_label={provider_label}",
        f"provider_planner={provider_planner}",
        f"provider_source={provider_source}",
        f"provider_ready={provider_ready}",
        f"current_reasoning_effort={current_reasoning_effort}",
        f"write_scope={write_scope}",
    ]
    if write_path:
        lines.append(f"write_path={write_path}")
    return lines


__all__ = [
    "model_selection_lines",
    "model_status_lines",
    "provider_probe_lines",
    "provider_summary_lines",
    "provider_switch_headline",
    "provider_verbose_lines",
]
