from __future__ import annotations

from cli.agent_cli.core.provider_session import ProviderToolCall
from cli.agent_cli.providers.delegation_policy import (
    DELEGATION_MODE_VALUES,
    DELEGATION_TASK_SHAPES,
    SPAWN_AGENT_REASON_CODES,
    WAIT_AGENT_REASON_CODES,
    apply_planner_delegation_defaults,
    delegation_policy_prompt_text,
    infer_spawn_agent_metadata,
    planner_tool_execution_target,
    planner_trace_delegation_summary,
    resolve_spawn_agent_async_mode,
)


def test_delegation_policy_public_reason_and_shape_contracts_are_frozen() -> None:
    assert SPAWN_AGENT_REASON_CODES == (
        "research_side_task",
        "verify_side_task",
        "long_running_exec",
        "background_side_task",
    )
    assert WAIT_AGENT_REASON_CODES == ("wait_for_child_result",)
    assert DELEGATION_MODE_VALUES == ("sync", "background")
    assert DELEGATION_TASK_SHAPES == (
        "read_only",
        "workspace_mutating",
        "context_sensitive",
        "long_running",
    )

def test_infer_spawn_agent_metadata_marks_research_side_task_as_background_read_only() -> None:
    metadata = infer_spawn_agent_metadata(
        {"task": "调研当前 provider 文档并收集参考链接"},
        async_mode=True,
    )

    assert metadata == {
        "delegation_reason": "research_side_task",
        "delegation_mode": "background",
        "task_shape": "read_only",
        "wait_required": False,
    }

def test_infer_spawn_agent_metadata_marks_context_sensitive_followup() -> None:
    metadata = infer_spawn_agent_metadata(
        {"task": "Continue current task using current context and above conversation"},
        async_mode=True,
    )

    assert metadata["delegation_reason"] == "background_side_task"
    assert metadata["delegation_mode"] == "background"
    assert metadata["task_shape"] == "context_sensitive"
    assert metadata["wait_required"] is False

def test_infer_spawn_agent_metadata_marks_workspace_mutating_code_change() -> None:
    metadata = infer_spawn_agent_metadata(
        {"task": "Modify current file and implement patch"},
        async_mode=False,
    )

    assert metadata["delegation_reason"] == "background_side_task"
    assert metadata["delegation_mode"] == "sync"
    assert metadata["task_shape"] == "workspace_mutating"
    assert metadata["wait_required"] is False

def test_apply_planner_delegation_defaults_make_teammate_background_by_default() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "收集 provider 文档差异",
            "role": "teammate",
        },
    )

    assert payload["async"] is True
    assert payload["reason"] == "research_side_task"
    assert payload["mode"] == "background"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "read_only"

def test_apply_planner_delegation_defaults_preserve_explicit_teammate_sync_override() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "Continue current task using current context",
            "role": "teammate",
            "async": False,
        },
    )

    assert payload["async"] is False
    assert payload["mode"] == "sync"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "context_sensitive"

def test_apply_planner_delegation_defaults_context_sensitive_teammate_defaults_to_sync() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "Continue current task using current context and above conversation",
            "role": "teammate",
        },
    )

    assert "async" not in payload
    assert payload["mode"] == "sync"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "context_sensitive"

def test_apply_planner_delegation_defaults_long_running_subagent_defaults_to_background() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "运行 benchmark 收集 provider 延迟数据",
            "role": "subagent",
        },
    )

    assert payload["async"] is True
    assert payload["mode"] == "background"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "long_running"

def test_apply_planner_delegation_defaults_workspace_mutating_subagent_stays_sync() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "修改当前文件并实现补丁",
            "role": "subagent",
        },
    )

    assert "async" not in payload
    assert payload["mode"] == "sync"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "workspace_mutating"

def test_apply_planner_delegation_defaults_context_sensitive_subagent_stays_sync() -> None:
    payload = apply_planner_delegation_defaults(
        "spawn_agent",
        {
            "task": "Continue current task using current context and decide the next step",
            "role": "subagent",
        },
    )

    assert "async" not in payload
    assert payload["mode"] == "sync"
    assert payload["wait_required"] is False
    assert payload["task_shape"] == "context_sensitive"

def test_delegation_policy_prompt_text_explicitly_blocks_mainline_reasoning_delegation() -> None:
    prompt = delegation_policy_prompt_text()

    assert "Keep tightly coupled user-facing reasoning" in prompt
    assert "immediate code-edit decisions" in prompt
    assert "agent_workflow is an AgentHub extension" in prompt
    assert "Do not busy-wait on background agents" in prompt

def test_delegation_policy_prompt_text_projects_codex_and_claude_surface_differences() -> None:
    codex_prompt = delegation_policy_prompt_text(tool_surface_profile="codex_openai")
    claude_prompt = delegation_policy_prompt_text(tool_surface_profile="claude_code")

    assert "Default Codex-aligned model-facing surfaces do not expose delegation or child-lifecycle tools." in codex_prompt
    assert "Do not invent spawn_agent, send_input, resume_agent, wait, close_agent" in codex_prompt
    assert "Use Agent only for bounded side tasks" in claude_prompt
    assert "Use SendMessage only to continue an existing delegated child by id" in claude_prompt
    assert "notification-driven rather than poll-driven" in claude_prompt

def test_apply_planner_delegation_defaults_normalizes_claude_agent_projection_arguments() -> None:
    payload = apply_planner_delegation_defaults(
        "Agent",
        {
            "prompt": "运行 benchmark 收集 provider 延迟数据",
            "run_in_background": True,
        },
    )

    assert payload["task"] == "运行 benchmark 收集 provider 延迟数据"
    assert payload["async"] is True
    assert payload["reason"] == "long_running_exec"
    assert payload["mode"] == "background"
    assert payload["task_shape"] == "long_running"


def test_codex_collab_spawn_agent_defaults_to_async_creation() -> None:
    assert (
        resolve_spawn_agent_async_mode(
            {
                "task": "Reply with exactly ONE and nothing else.",
                "codex_collab_payload": True,
                "source_message": "Reply with exactly ONE and nothing else.",
            },
            role="subagent",
        )
        is True
    )

def test_planner_tool_execution_target_normalizes_projected_send_message_and_wait_names() -> None:
    send_tool_name, send_arguments = planner_tool_execution_target(
        "SendMessage",
        {
            "to": "agent_1",
            "message": "继续检查",
        },
    )
    wait_tool_name, wait_arguments = planner_tool_execution_target(
        "wait",
        {
            "target": "agent_1",
            "wait_required": False,
            "timeout_ms": 250,
        },
    )

    assert send_tool_name == "send_input"
    assert send_arguments == {
        "target": "agent_1",
        "message": "继续检查",
    }
    assert wait_tool_name == "agent_workflow"
    assert wait_arguments == {
        "target": "agent_1",
    }

def test_planner_trace_delegation_summary_stays_local_without_delegation_tools() -> None:
    summary = planner_trace_delegation_summary([])

    assert summary["delegation_decision"] == "none"
    assert summary["delegation_policy_decision"] == "stay_local"
    assert summary["delegation_policy_source"] == "delegation_policy"
    assert summary["delegation_policy_reason"] == "no_delegation_tools_observed"
    assert summary["delegation_policy_input_source"] == "tool_calls"
    assert summary["delegation_stay_local_source"] == "planner_tool_calls"
    assert summary["delegation_stay_local_reason"] == "no_tools_observed"
    assert summary["observed_tool_count"] == 0
    assert summary["observed_delegation_tool_count"] == 0
    assert summary["observed_non_delegation_tool_count"] == 0

def test_planner_trace_delegation_summary_keeps_regular_tool_execution_local() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="exec_command",
                arguments={"cmd": "pytest -q cli/tests/test_delegation_policy.py"},
            )
        ]
    )

    assert summary["delegation_decision"] == "none"
    assert summary["delegation_policy_decision"] == "stay_local"
    assert summary["delegation_policy_reason"] == "no_delegation_tools_observed"
    assert summary["delegation_stay_local_source"] == "planner_tool_calls"
    assert summary["delegation_stay_local_reason"] == "non_delegation_tools_only"
    assert summary["delegation_stay_local_counterexamples"] == ["exec_command"]
    assert summary["observed_tool_count"] == 1
    assert summary["observed_delegation_tool_count"] == 0
    assert summary["observed_non_delegation_tool_count"] == 1
    assert summary["observed_tool_names"] == ["exec_command"]
    assert summary["observed_non_delegation_tool_names"] == ["exec_command"]

def test_planner_trace_delegation_summary_prefers_wait_later_for_agent_workflow_snapshot() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="agent_workflow",
                arguments={"target": "agent_1", "steps": 3},
            )
        ]
    )

    assert summary["delegation_decision"] == "none"
    assert summary["delegation_policy_decision"] == "wait_later"
    assert summary["delegation_policy_source"] == "delegation_policy"
    assert summary["delegation_policy_reason"] == "agent_workflow_snapshot"
    assert summary["observed_tool_count"] == 1
    assert summary["observed_delegation_tool_count"] == 1
    assert summary["observed_non_delegation_tool_count"] == 0
    assert summary["observed_tool_names"] == ["agent_workflow"]
    action = summary["delegation_actions"][0]
    assert action["tool_name"] == "agent_workflow"
    assert action["target"] == "agent_1"
    assert action["planner_policy"] == "wait_later"
    assert action["policy_basis"] == "explicit_arguments"
    assert action["execution_tool"] == "agent_workflow"
    assert action["execution_mode"] == "parallel"

def test_planner_trace_delegation_summary_tracks_stay_local_counterexamples_for_multiple_non_delegation_tools() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="exec_command",
                arguments={"cmd": "pytest -q"},
            ),
            ProviderToolCall(
                call_id="call_2",
                name="read_file",
                arguments={"path": "README.md"},
            ),
        ]
    )

    assert summary["delegation_decision"] == "none"
    assert summary["delegation_policy_decision"] == "stay_local"
    assert summary["delegation_stay_local_reason"] == "non_delegation_tools_only"
    assert summary["delegation_stay_local_counterexamples"] == ["exec_command", "read_file"]
    assert summary["observed_tool_count"] == 2
    assert summary["observed_delegation_tool_count"] == 0
    assert summary["observed_non_delegation_tool_count"] == 2

def test_planner_trace_delegation_summary_tracks_stay_local_counterexamples_with_mixed_non_delegation_sequence() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="exec_command",
                arguments={"cmd": "pytest -q"},
            ),
            ProviderToolCall(
                call_id="call_2",
                name="read_file",
                arguments={"path": "README.md"},
            ),
            ProviderToolCall(
                call_id="call_3",
                name="exec_command",
                arguments={"cmd": "git status --short"},
            ),
        ]
    )

    assert summary["delegation_policy_decision"] == "stay_local"
    assert summary["delegation_policy_reason"] == "no_delegation_tools_observed"
    assert summary["delegation_stay_local_reason"] == "non_delegation_tools_only"
    assert summary["delegation_stay_local_counterexamples"] == ["exec_command", "read_file", "exec_command"]
    assert summary["observed_tool_names"] == ["exec_command", "read_file", "exec_command"]
    assert summary["observed_non_delegation_tool_names"] == ["exec_command", "read_file", "exec_command"]

def test_planner_trace_delegation_summary_does_not_mark_stay_local_when_spawn_and_non_delegation_tools_mix() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="exec_command",
                arguments={"cmd": "pytest -q"},
            ),
            ProviderToolCall(
                call_id="call_2",
                name="spawn_agent",
                arguments={
                    "task": "运行 benchmark 收集 provider 延迟数据",
                    "role": "subagent",
                },
            ),
        ]
    )

    assert summary["delegation_decision"] == "delegate"
    assert summary["delegation_policy_decision"] == "delegate_async"
    assert summary["delegation_policy_reason"] == "spawn_agent"
    assert "delegation_stay_local_reason" not in summary
    assert "delegation_stay_local_counterexamples" not in summary
    assert summary["observed_tool_count"] == 2
    assert summary["observed_delegation_tool_count"] == 1
    assert summary["observed_non_delegation_tool_count"] == 1
    assert summary["observed_tool_names"] == ["exec_command", "spawn_agent"]
    assert summary["observed_non_delegation_tool_names"] == ["exec_command"]

def test_planner_trace_delegation_summary_records_spawn_default_sources() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="spawn_agent",
                arguments={
                    "task": "运行 benchmark 收集 provider 延迟数据",
                    "role": "subagent",
                    "async": True,
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert summary["delegation_policy_reason"] == "spawn_agent"
    assert action["execution_tool"] == "spawn_agent"
    assert action["defaulted_fields"] == ["reason", "mode", "wait_required", "task_shape"]
    assert action["policy_basis"] == "task_text_inference+delegation_policy_defaults"


def test_planner_trace_delegation_summary_exposes_minimum_spawn_contract_fields() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="spawn_agent",
                arguments={
                    "task": "运行 benchmark 收集 provider 延迟数据",
                    "role": "subagent",
                },
            )
        ]
    )

    assert summary["delegation_decision"] == "delegate"
    assert summary["delegation_reason"] == "long_running_exec"
    assert summary["delegation_mode"] == "background"
    assert summary["wait_required"] is False
    assert summary["task_shape"] == "long_running"

def test_planner_trace_delegation_summary_marks_context_sensitive_teammate_as_delegate_sync() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="spawn_agent",
                arguments={
                    "task": "Continue current task using current context and above conversation",
                    "role": "teammate",
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert summary["delegation_policy_decision"] == "delegate_sync"
    assert summary["delegation_policy_reason"] == "spawn_agent"
    assert action["planner_policy"] == "delegate_sync"
    assert action["task_shape"] == "context_sensitive"
    assert action["policy_basis"] == "task_text_inference+delegation_policy_defaults"

def test_planner_trace_delegation_summary_marks_long_running_subagent_as_delegate_async() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="spawn_agent",
                arguments={
                    "task": "运行 benchmark 收集 provider 延迟数据",
                    "role": "subagent",
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert summary["delegation_policy_decision"] == "delegate_async"
    assert action["planner_policy"] == "delegate_async"
    assert action["execution_tool"] == "spawn_agent"
    assert action["task_shape"] == "long_running"
    assert "async" in action["defaulted_fields"]

def test_planner_trace_delegation_summary_marks_non_blocking_wait_as_snapshot() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="wait_agent",
                arguments={
                    "target": "agent_1",
                    "wait_required": False,
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert summary["delegation_decision"] == "wait"
    assert summary["delegation_policy_decision"] == "wait_later"
    assert summary["delegation_policy_reason"] == "wait_agent_non_blocking_snapshot"
    assert action["planner_policy"] == "wait_later"
    assert action["preferred_snapshot_tool"] == "agent_workflow"
    assert action["execution_tool"] == "agent_workflow"
    assert action["defaulted_fields"] == ["reason"]
    assert action["policy_basis"] == "wait_reason_default"

def test_planner_trace_delegation_summary_normalizes_claude_agent_surface() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="Agent",
                arguments={
                    "prompt": "运行 benchmark 收集 provider 延迟数据",
                    "run_in_background": True,
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert summary["delegation_decision"] == "delegate"
    assert summary["delegation_policy_reason"] == "spawn_agent"
    assert summary["observed_tool_names"] == ["spawn_agent"]
    assert action["tool_name"] == "spawn_agent"
    assert action["execution_tool"] == "spawn_agent"
    assert action["planner_policy"] == "delegate_async"
    assert action["async"] is True

def test_planner_trace_delegation_summary_includes_wait_timeout_budget_from_arguments() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="wait_agent",
                arguments={
                    "target": "agent_1",
                    "timeout_ms": 250,
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert action["wait_timeout_ms"] == 250
    assert summary["wait_timeout_ms"] == 250
    assert summary["delegation_budget_source"] == "planner_arguments"
    assert "wait_timeout_ms" in summary["delegation_budget_fields"]
    assert summary["delegation_strategy"] == "downgrade_continue"
    assert summary["delegation_strategy_reason"] == "budget_not_hit"
    assert summary["delegation_continue_main_thread"] is True

def test_planner_trace_delegation_summary_includes_spawn_timeout_budget_from_arguments() -> None:
    summary = planner_trace_delegation_summary(
        [
            ProviderToolCall(
                call_id="call_1",
                name="spawn_agent",
                arguments={
                    "task": "运行 benchmark 收集 provider 延迟数据",
                    "role": "subagent",
                    "timeout": 18,
                },
            )
        ]
    )

    action = summary["delegation_actions"][0]
    assert action["timeout_budget_seconds"] == 18
    assert summary["timeout_budget_seconds"] == 18
    assert summary["delegation_budget_source"] == "planner_arguments"
    assert "timeout_budget_seconds" in summary["delegation_budget_fields"]
    assert summary["delegation_strategy"] == "downgrade_continue"
    assert summary["delegation_strategy_reason"] == "budget_not_hit"
    assert summary["delegation_continue_main_thread"] is True

def test_planner_tool_execution_target_rewrites_non_blocking_wait_to_agent_workflow() -> None:
    tool_name, arguments = planner_tool_execution_target(
        "wait_agent",
        {
            "target": "agent_1",
            "wait_required": False,
            "timeout_ms": 250,
        },
    )

    assert tool_name == "agent_workflow"
    assert arguments == {
        "target": "agent_1",
    }
