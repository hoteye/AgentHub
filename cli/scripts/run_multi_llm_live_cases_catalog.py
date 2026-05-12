from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiveCase:
    name: str
    phase: str
    prompt: str
    commands: tuple[str, ...] = ()
    setup_commands: tuple[str, ...] = ()
    role: str = ""
    spawn_overrides: dict[str, Any] | None = None
    expected_delegated_source: str = ""
    expected_delegation_mode: str = ""
    expected_task_shape: str = ""
    expected_wait_required: bool | None = None
    expected_background_priority: str = ""
    expected_spawn_agent: bool | None = None
    expected_orchestration_decision: str = ""
    expected_stay_local_reason: str = ""
    expected_stay_local_counterexamples: tuple[str, ...] = ()
    wait_timeout_ms: int = 0
    wait_reason: str = ""
    wait_required: bool | None = None
    profiles: tuple[str, ...] = ("orchestration_smoke",)


CASES: tuple[LiveCase, ...] = (
    LiveCase(
        name="followup_pwd",
        phase="tool_followup",
        prompt="根据当前已验证的工具结果，直接回答当前工作目录，只输出最终答案。",
        commands=("pwd",),
        expected_spawn_agent=False,
        profiles=("orchestration_smoke", "orchestration_matrix", "focused_delegation_matrix", "core_matrix"),
    ),
    LiveCase(
        name="followup_git_status",
        phase="tool_followup",
        prompt="根据当前已验证的工具结果，直接说明当前工作区是否干净，并列出未提交路径；不要给建议。",
        commands=("git status --short",),
        expected_spawn_agent=False,
        profiles=("orchestration_smoke", "orchestration_matrix", "focused_delegation_matrix"),
    ),
    LiveCase(
        name="synthesis_workspace_state",
        phase="final_synthesis",
        prompt=(
            "根据当前已验证的工具结果，用两句中文总结当前仓库状态："
            "第一句回答当前目录与当前分支，第二句回答是否存在未提交改动并点名关键路径。"
        ),
        commands=("pwd", "git rev-parse --abbrev-ref HEAD", "git status --short"),
        expected_spawn_agent=False,
        profiles=("orchestration_smoke", "orchestration_matrix", "focused_delegation_matrix", "core_matrix"),
    ),
    LiveCase(
        name="delegate_subagent_git_status",
        phase="spawn_agent",
        prompt="检查当前仓库状态，只用两句中文回答：第一句给出当前分支，第二句只回答工作区是否干净；不要列出路径，也不要给建议。",
        setup_commands=(
            "/delegate-model subagent glm_5 --provider glm --reasoning-effort medium --timeout 30",
        ),
        role="subagent",
        profiles=("orchestration_smoke", "orchestration_matrix", "focused_delegation_matrix", "core_matrix"),
    ),
    LiveCase(
        name="delegate_teammate_background_verify",
        phase="spawn_agent",
        prompt="检查当前仓库根目录，挑两个最值得后续验证的顶层对象，并各给一句不超过十个字的中文说明。",
        role="teammate",
        spawn_overrides={
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "timeout": 30,
        },
        expected_delegation_mode="background",
        expected_task_shape="read_only",
        expected_wait_required=False,
        expected_background_priority="low",
        wait_timeout_ms=60000,
        wait_reason="wait_for_child_result",
        wait_required=True,
        profiles=("orchestration_smoke", "orchestration_matrix", "focused_delegation_matrix", "core_matrix"),
    ),
    LiveCase(
        name="delegate_teammate_workspace_summary",
        phase="spawn_agent",
        prompt="查看当前仓库根目录，列出最值得先看的三个顶层目录或文件，并给每个对象附一段不超过十个字的中文说明。",
        role="teammate",
        setup_commands=(
            "/delegate-model teammate glm_5 --provider glm --reasoning-effort medium --timeout 30",
        ),
        expected_delegated_source="session_override",
        expected_delegation_mode="background",
        expected_task_shape="read_only",
        expected_wait_required=False,
        expected_background_priority="low",
    ),
    LiveCase(
        name="delegate_teammate_background_briefing",
        phase="spawn_agent",
        prompt="后台查看当前仓库根目录，用中文给出两个最值得先读的入口，每个入口附一句不超过十二个字的说明。",
        role="teammate",
        spawn_overrides={
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "timeout": 30,
            "reason": "research_side_task",
        },
        expected_delegation_mode="background",
        expected_task_shape="read_only",
        expected_wait_required=False,
        expected_background_priority="low",
        profiles=("orchestration_smoke",),
    ),
    LiveCase(
        name="delegate_teammate_parallel_verify_readme",
        phase="spawn_agent",
        prompt="后台并行检查 README 和 docs 入口是否存在明显缺失，只给两句中文结论，不要修改文件。",
        role="teammate",
        spawn_overrides={
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "timeout": 30,
            "reason": "verify_side_task",
        },
        expected_delegation_mode="background",
        expected_task_shape="read_only",
        expected_wait_required=False,
        expected_background_priority="low",
        wait_timeout_ms=60000,
        wait_reason="wait_for_child_result",
        wait_required=True,
    ),
    LiveCase(
        name="orchestrate_background_teammate_smoke",
        phase="orchestrate_background_teammate",
        prompt=(
            "background teammate modify orchestration status summary; "
            "owned_files: cli/agent_cli/runtime.py; "
            "acceptance_criteria: background teammate dispatch ref captured"
        ),
        profiles=("orchestration_background_teammate", "orchestration_smoke", "core_matrix"),
    ),
)


PROFILE_CHOICES = (
    "all",
    "orchestration_smoke",
    "orchestration_matrix",
    "orchestration_background_teammate",
    "focused_delegation_matrix",
    "core_matrix",
)

CI_REUSE_RECOMMENDED_COMMANDS = {
    "core_matrix": (
        "python cli/scripts/run_multi_llm_live_cases.py "
        "--profile core_matrix --strict "
        "--out /tmp/agenthub_multi_llm_core_matrix_report.json"
    ),
    "focused_delegation_matrix": (
        "python cli/scripts/run_multi_llm_live_cases.py "
        "--profile focused_delegation_matrix --strict "
        "--out /tmp/agenthub_multi_llm_focused_delegation_report.json"
    ),
    "orchestration_matrix": (
        "python cli/scripts/run_multi_llm_live_cases.py "
        "--profile orchestration_matrix --strict "
        "--out /tmp/agenthub_multi_llm_matrix_report.json"
    ),
}
