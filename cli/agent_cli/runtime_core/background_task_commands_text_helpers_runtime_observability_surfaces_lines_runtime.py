from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_surfaces_runtime import (
    observability_value_impl,
    orchestration_budget_surface_impl,
    orchestration_reason_surface_impl,
    trace_bool_impl,
)


def command_policy_surface_impl(value: Any) -> tuple[int, int, int, str]:
    entries: list[dict[str, Any]] = []
    if isinstance(value, list):
        entries = [item for item in value if isinstance(item, dict)]
    elif isinstance(value, dict):
        entries = [value]
    if not entries:
        return 0, 0, 0, ""
    denied = [item for item in entries if bool(item.get("policy_denied"))]
    if denied:
        denied_cmd = str(denied[0].get("command") or denied[0].get("effective_command") or "").strip()
        return len(denied), 0, 0, f"policy denied: {denied_cmd}" if denied_cmd else "policy denied"
    rewritten: list[tuple[str, str]] = []
    for item in entries:
        command = str(item.get("command") or "").strip()
        effective = str(item.get("effective_command") or "").strip()
        if command and effective and command != effective:
            rewritten.append((command, effective))
    if rewritten:
        src, dst = rewritten[0]
        return 0, len(rewritten), 0, f"policy rewrite: {src} -> {dst}"
    return 0, 0, len(entries), f"policy checked: {len(entries)}"


def append_observability_surface_lines_impl(
    lines: list[str],
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> None:
    for key in (
        "delegation_decision",
        "delegation_policy_decision",
        "delegation_policy_source",
        "delegation_policy_reason",
        "delegation_execution_mode",
        "delegation_execution_reason",
        "delegation_reason",
        "delegation_mode",
        "wait_reason",
        "task_shape",
        "scheduler_reason",
        "parallel_group",
        "parallel_limit",
        "delegation_strategy",
        "delegation_strategy_reason",
        "delegation_strategy_source",
        "delegation_budget_source",
        "delegation_observation_source",
        "delegation_outcome",
        "delegation_timeout_reason",
        "delegation_failure_reason",
    ):
        value = observability_value_impl(
            key,
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        rendered = str(value or "").strip()
        if rendered:
            lines.append(f"{key}={rendered}")
    wait_required = trace_bool_impl(
        observability_value_impl(
            "wait_required",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    )
    if wait_required is not None:
        lines.append(f"wait_required={'true' if wait_required else 'false'}")
    for key in (
        "delegation_continue_main_thread",
        "delegation_budget_hit",
        "delegation_timeout_hit",
        "delegation_cancelled",
        "delegation_failed",
    ):
        value = trace_bool_impl(
            observability_value_impl(
                key,
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
        )
        if value is not None:
            lines.append(f"{key}={'true' if value else 'false'}")
    reason_surface = orchestration_reason_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )
    if reason_surface:
        lines.append(f"delegation_reason_surface={reason_surface}")
    budget_surface = orchestration_budget_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )
    if budget_surface:
        lines.append(f"delegation_budget_surface={budget_surface}")
    for key in (
        "tool_event_names",
        "modified_files",
        "commands",
        "test_commands",
        "command_policies",
        "allowed_paths",
        "blocked_paths",
        "out_of_scope_files",
        "review_commands",
        "applied_files",
        "policy_helper_helper_combo_ids",
        "policy_helper_override",
        "route_report",
        "delegation_actions",
        "delegation_outcomes",
        "delegation_budget_fields",
        "delegation_budget_snapshot",
    ):
        value = observability_value_impl(
            key,
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        if value is not None:
            lines.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    command_policies = observability_value_impl(
        "command_policies",
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )
    denied_count, rewrite_count, checked_count, policy_surface = command_policy_surface_impl(command_policies)
    if denied_count > 0:
        lines.append(f"command_policy_denied_count={denied_count}")
    if rewrite_count > 0:
        lines.append(f"command_policy_rewrite_count={rewrite_count}")
    if checked_count > 0:
        lines.append(f"command_policy_checked_count={checked_count}")
    if policy_surface:
        lines.append(f"command_policy_surface={policy_surface}")
