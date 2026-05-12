from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cli.agent_cli.providers import delegation_policy_mapping_runtime
from cli.agent_cli.providers import delegation_policy_runtime as delegation_policy_runtime_service

SPAWN_AGENT_REASON_CODES: tuple[str, ...] = (
    "research_side_task",
    "verify_side_task",
    "long_running_exec",
    "background_side_task",
)

WAIT_AGENT_REASON_CODES: tuple[str, ...] = ("wait_for_child_result",)

RECOVER_AGENT_ACTION_VALUES: tuple[str, ...] = (
    "retry_step",
    "resume_session",
    "close_session",
)

SPAWN_AGENT_ROLE_VALUES: tuple[str, ...] = ("subagent", "teammate")

DELEGATION_MODE_VALUES: tuple[str, ...] = ("sync", "background")

DELEGATION_TASK_SHAPES: tuple[str, ...] = (
    "read_only",
    "workspace_mutating",
    "context_sensitive",
    "long_running",
)

_ORCHESTRATION_CONTINUE_DECISIONS: tuple[str, ...] = (
    "delegate",
    "delegate_async",
    "delegate_sync",
    "delegate_and_wait",
    "wait",
    "wait_now",
    "wait_later",
    "retry_child",
    "resume_child",
)

_ORCHESTRATION_WAIT_DECISIONS: tuple[str, ...] = (
    "wait",
    "wait_now",
    "delegate_and_wait",
)

_ORCHESTRATION_DOWNGRADE_DECISIONS: tuple[str, ...] = ("delegate_sync",)

_ORCHESTRATION_STOP_DECISIONS: tuple[str, ...] = ("close_child",)


def _delegation_control_action(summary: dict[str, Any]) -> dict[str, Any]:
    decision = (
        str(
            summary.get("delegation_policy_decision") or summary.get("orchestration_decision") or ""
        )
        .strip()
        .lower()
    )
    policy_reason = (
        str(
            summary.get("delegation_policy_reason")
            or summary.get("orchestration_policy_reason")
            or ""
        )
        .strip()
        .lower()
    )
    execution_mode = (
        str(
            summary.get("delegation_execution_mode")
            or summary.get("orchestration_execution_mode")
            or ""
        )
        .strip()
        .lower()
    )
    if not decision or decision == "none":
        decision = "stay_local"
    if decision == "stay_local":
        return {
            "delegation_control_action": "stay_local",
            "delegation_control_reason": (
                "non_delegation_tools_only"
                if policy_reason == "no_delegation_tools_observed"
                and bool(summary.get("observed_non_delegation_tool_count"))
                else (policy_reason or "no_delegation_tools_observed")
            ),
            "delegation_control_continue_main_thread": True,
            "delegation_control_wait_for_child": False,
            "delegation_control_stop_early": False,
            "delegation_control_source": "delegation_policy",
        }
    if decision in _ORCHESTRATION_STOP_DECISIONS:
        return {
            "delegation_control_action": "stop",
            "delegation_control_reason": policy_reason or f"decision:{decision}",
            "delegation_control_continue_main_thread": False,
            "delegation_control_wait_for_child": False,
            "delegation_control_stop_early": True,
            "delegation_control_source": "delegation_policy",
        }
    if decision in _ORCHESTRATION_WAIT_DECISIONS:
        return {
            "delegation_control_action": "wait",
            "delegation_control_reason": policy_reason or f"decision:{decision}",
            "delegation_control_continue_main_thread": False,
            "delegation_control_wait_for_child": True,
            "delegation_control_stop_early": False,
            "delegation_control_source": "delegation_policy",
        }
    if decision in _ORCHESTRATION_DOWNGRADE_DECISIONS or execution_mode == "serial":
        return {
            "delegation_control_action": "downgrade",
            "delegation_control_reason": (
                "serialized_delegation_path"
                if decision in _ORCHESTRATION_DOWNGRADE_DECISIONS and not policy_reason
                else (policy_reason or f"decision:{decision}")
            ),
            "delegation_control_continue_main_thread": True,
            "delegation_control_wait_for_child": False,
            "delegation_control_stop_early": False,
            "delegation_control_source": "delegation_policy",
        }
    continue_delegation = decision in _ORCHESTRATION_CONTINUE_DECISIONS
    return {
        "delegation_control_action": "continue" if continue_delegation else "stop",
        "delegation_control_reason": policy_reason or f"decision:{decision}",
        "delegation_control_continue_main_thread": continue_delegation,
        "delegation_control_wait_for_child": False,
        "delegation_control_stop_early": not continue_delegation,
        "delegation_control_source": "delegation_policy",
    }


def delegation_policy_prompt_text(*, tool_surface_profile: str = "") -> str:
    profile = str(tool_surface_profile or "").strip().lower()
    if profile == "codex_openai":
        return (
            "Default Codex-aligned model-facing surfaces do not expose delegation or child-lifecycle tools. "
            "Keep bounded side-task delegation, child control, and legacy taskbook escalation out of the default model-facing path unless an explicit collab surface is exposed. "
            "Keep tightly coupled user-facing reasoning and immediate code-edit decisions in the main thread. "
            "Do not invent spawn_agent, send_input, resume_agent, wait, close_agent, agent_workflow, or recover_agent unless they are actually exposed. "
            "Do not assume AgentHub-only extensions are part of the native Codex default tool surface."
        )
    if profile == "claude_code":
        return (
            "Use Agent only for bounded side tasks that can run semi-independently from the mainline, "
            "such as independent research, parallel verification, or long-running benchmark/exec work. "
            "Keep tightly coupled user-facing reasoning and immediate code-edit decisions in the main thread. "
            "Prefer foreground Agent calls, or staying local, for context-sensitive follow-ups and workspace-mutating tasks. "
            "Long-running benchmark/exec work is a better candidate for run_in_background=true. "
            "Use SendMessage only to continue an existing delegated child by id; it is also the follow-up/resume surface in this profile. "
            "Background Agent launches are notification-driven rather than poll-driven, so do not invent wait_agent, resume_agent, close_agent, agent_workflow, recover_agent, TaskStop, team_name, isolation, or remote controls unless they are actually exposed. "
            "Do not busy-wait on background agents without a clear join plan."
        )
    return (
        "Use spawn_agent only for bounded side tasks that can run semi-independently from the mainline, "
        "such as independent research, parallel verification, or long-running benchmark/exec work. "
        "Keep tightly coupled user-facing reasoning and immediate code-edit decisions in the main thread. "
        "Prefer sync delegation, or staying local, for context-sensitive follow-ups and workspace-mutating tasks. "
        "Long-running benchmark/exec work is a better candidate for background delegation. "
        "Use async=true only when the child result can arrive later without blocking the immediate next step. "
        "Use wait_agent only when the next step explicitly depends on that delegated result. "
        "Prefer agent_workflow when you only need a non-blocking child status or recovery snapshot; agent_workflow is an AgentHub extension, not Codex or Claude parity. "
        "Use spawn_child_tab/send_child_tab/wait_child_tasks only when visible child tabs are intentionally exposed and the user should be able to watch or steer the child execution. "
        'For visible children, consume normalized TaskRun snapshots from wait_child_tasks instead of scraping child transcripts; use wait_child_tasks(wait_for="any") when progressive summarization should continue after the first selected child returns. '
        "Use recover_agent with retry_step when a delegated workflow exposes a recoverable failed step and retrying the child is cheaper than spawning a duplicate task. "
        "Do not busy-wait on background agents without a clear join plan."
    )


def _normalized_enum(value: Any, allowed: tuple[str, ...]) -> str | None:
    return delegation_policy_mapping_runtime.normalized_enum(value, allowed)


def _normalized_bool(value: Any) -> bool | None:
    return delegation_policy_mapping_runtime.normalized_bool(value)


def _argument_is_supplied(payload: dict[str, Any], key: str) -> bool:
    return delegation_policy_mapping_runtime.argument_is_supplied(payload, key)


def _normalized_number(value: Any) -> int | float | None:
    return delegation_policy_mapping_runtime.normalized_number(value)


def _normalized_int(value: Any) -> int | None:
    return delegation_policy_mapping_runtime.normalized_int(value)


def _timeout_budget_seconds(payload: dict[str, Any]) -> int | float | None:
    return delegation_policy_mapping_runtime.timeout_budget_seconds(payload)


def _wait_timeout_ms(payload: dict[str, Any]) -> int | None:
    return delegation_policy_mapping_runtime.wait_timeout_ms(payload)


def normalize_spawn_agent_role(value: Any) -> str:
    return delegation_policy_mapping_runtime.normalize_spawn_agent_role(
        value,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def resolve_spawn_agent_async_mode(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
) -> bool:
    return delegation_policy_mapping_runtime.resolve_spawn_agent_async_mode(
        arguments,
        async_mode=async_mode,
        role=role,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def normalize_spawn_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    return delegation_policy_mapping_runtime.normalize_spawn_agent_metadata(
        arguments,
        async_mode=async_mode,
        role=role,
        reason_codes=SPAWN_AGENT_REASON_CODES,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        task_shapes=DELEGATION_TASK_SHAPES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def normalize_wait_agent_metadata(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return delegation_policy_mapping_runtime.normalize_wait_agent_metadata(
        arguments,
        wait_reason_codes=WAIT_AGENT_REASON_CODES,
    )


def normalize_recover_agent_metadata(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return delegation_policy_mapping_runtime.normalize_recover_agent_metadata(
        arguments,
        recovery_action_values=RECOVER_AGENT_ACTION_VALUES,
    )


def _normalized_text(value: Any) -> str:
    return delegation_policy_runtime_service.normalized_text(value)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return delegation_policy_runtime_service.contains_any(text, hints)


def _spawn_task_text(arguments: dict[str, Any] | None) -> str:
    return delegation_policy_runtime_service.spawn_task_text(arguments)


def infer_spawn_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    return delegation_policy_mapping_runtime.infer_spawn_agent_metadata(
        arguments,
        async_mode=async_mode,
        role=role,
        reason_codes=SPAWN_AGENT_REASON_CODES,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        task_shapes=DELEGATION_TASK_SHAPES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def _planner_defaulted_fields(
    raw_arguments: dict[str, Any],
    enriched_arguments: dict[str, Any],
    *,
    field_names: tuple[str, ...],
) -> list[str]:
    return delegation_policy_runtime_service.planner_defaulted_fields(
        raw_arguments,
        enriched_arguments,
        field_names=field_names,
        argument_is_supplied_fn=_argument_is_supplied,
    )


def _planner_policy_basis(
    tool_name: str,
    raw_arguments: dict[str, Any],
    enriched_arguments: dict[str, Any],
    *,
    defaulted_fields: list[str],
) -> str:
    return delegation_policy_runtime_service.planner_policy_basis(
        tool_name,
        raw_arguments,
        enriched_arguments,
        defaulted_fields=defaulted_fields,
        normalize_spawn_agent_role_fn=normalize_spawn_agent_role,
        spawn_task_text_fn=_spawn_task_text,
        argument_is_supplied_fn=_argument_is_supplied,
    )


def apply_planner_delegation_defaults(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    return delegation_policy_mapping_runtime.apply_planner_delegation_defaults(
        tool_name,
        arguments,
        reason_codes=SPAWN_AGENT_REASON_CODES,
        wait_reason_codes=WAIT_AGENT_REASON_CODES,
        recovery_action_values=RECOVER_AGENT_ACTION_VALUES,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        task_shapes=DELEGATION_TASK_SHAPES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def planner_tool_execution_target(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    return delegation_policy_mapping_runtime.planner_tool_execution_target(
        tool_name,
        arguments,
        reason_codes=SPAWN_AGENT_REASON_CODES,
        wait_reason_codes=WAIT_AGENT_REASON_CODES,
        recovery_action_values=RECOVER_AGENT_ACTION_VALUES,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        task_shapes=DELEGATION_TASK_SHAPES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
    )


def planner_trace_delegation_summary(tool_calls: Iterable[Any]) -> dict[str, Any]:
    summary = delegation_policy_mapping_runtime.planner_trace_delegation_summary(
        tool_calls,
        reason_codes=SPAWN_AGENT_REASON_CODES,
        wait_reason_codes=WAIT_AGENT_REASON_CODES,
        recovery_action_values=RECOVER_AGENT_ACTION_VALUES,
        delegation_mode_values=DELEGATION_MODE_VALUES,
        task_shapes=DELEGATION_TASK_SHAPES,
        role_values=SPAWN_AGENT_ROLE_VALUES,
        planner_defaulted_fields_fn=_planner_defaulted_fields,
        planner_policy_basis_fn=_planner_policy_basis,
    )
    control = _delegation_control_action(summary)
    for field_name, field_value in control.items():
        if field_value not in (None, ""):
            summary.setdefault(field_name, field_value)
    normalized_decision = (
        str(
            summary.get("delegation_policy_decision") or summary.get("orchestration_decision") or ""
        )
        .strip()
        .lower()
    )
    if normalized_decision and normalized_decision != "stay_local":
        continue_delegation = normalized_decision in _ORCHESTRATION_CONTINUE_DECISIONS
        strategy = "downgrade_continue" if continue_delegation else "stop_and_return"
        summary.setdefault("delegation_strategy", strategy)
        summary.setdefault(
            "delegation_strategy_reason",
            "budget_not_hit" if continue_delegation else "planner_terminal_decision",
        )
        summary.setdefault("delegation_continue_main_thread", continue_delegation)
    return summary
