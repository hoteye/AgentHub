from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli.agent_cli.acceptance_support import (
    spawn_agent_wave02_case_specs_runtime as spawn_agent_wave02_case_specs_runtime_service,
)
from cli.agent_cli.acceptance_support import (
    spawn_agent_wave02_report_runtime as spawn_agent_wave02_report_runtime_service,
)
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.builtin_provider_delegation_specs import visible_delegation_tool_order
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs import provider_tool_names

CLI_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CLI_ROOT.parent
DEFAULT_OUT_DIR = Path("/tmp/agenthub_spawn_agent_wave02_acceptance")
DEFAULT_AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"
SUITE_NAME = "spawn_agent_wave02_live_acceptance"
CONTRACT_VERSION = "wave02_task_c_live_cross_system_bundle_v1"
ALL_LANES = (
    "agenthub_codex_openai",
    "agenthub_claude_code",
    "agenthub_generic_chat",
    "codex_ref",
    "claude_code_ref",
)
ALL_CASE_IDS = (
    "case_a_one_shot_read_only",
    "case_b_background_join",
    "case_c_follow_up_existing_child",
    "case_d_stop_or_close_surface",
    "case_e_agenthub_control_plane",
)
RELEVANT_DELEGATION_NAMES = {
    "spawn_agent",
    "request_orchestration",
    "send_input",
    "resume_agent",
    "wait",
    "wait_agent",
    "close_agent",
    "agent_workflow",
    "recover_agent",
    "Agent",
    "SendMessage",
    "TaskStop",
}
CODEX_REFERENCE_FILES = (
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/src/tools/spec.rs",
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/src/tools/handlers/multi_agents.rs",
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/src/agent/control.rs",
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/tests/suite/subagent_notifications.rs",
)
CLAUDE_REFERENCE_FILES = (
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/AgentTool/AgentTool.tsx",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/AgentTool/prompt.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/AgentTool/runAgent.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/AgentTool/resumeAgent.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/SendMessageTool/SendMessageTool.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/TaskStopTool/TaskStopTool.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/shared/spawnMultiAgent.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools.ts",
)
TASK_B_BLOCKED_ASSUMPTIONS = (
    "AgentHub canonical delegated-child result_contract fields remain owned by Task B and are not re-frozen in this Task C bundle.",
    "Background completion notification, repeated wait-after-adoption truth, and close/recover terminal payload semantics remain Task B-dependent runtime evidence.",
    "Claude-style Agent background launch plus SendMessage auto-resume may be planned in surface terms here, but canonical child identity and replay truth still depend on Task B landing.",
)
DIFFERENCE_TAXONOMY = (
    {
        "kind": "projection_or_policy_difference",
        "definition": (
            "A deliberate visible-surface or prompting difference that remains compatible with the same bounded delegation goal."
        ),
    },
    {
        "kind": "unsupported_capability",
        "definition": "A source-backed reference feature with no current AgentHub parity surface in the compared lane.",
    },
    {
        "kind": "implementation_bug",
        "definition": "A live result that contradicts the intended surface or runtime contract and should trigger a code fix.",
    },
)
PARITY_GAP_NOTES = (
    {
        "gap_id": "codex_multi_wait_ids",
        "difference_kind": "unsupported_capability",
        "source_paths": list(CODEX_REFERENCE_FILES[:2]),
        "reference_behavior": "Codex wait accepts ids[] and can return whichever child finishes first.",
        "agenthub_current_behavior": "AgentHub visible wait contract remains single-target target=agent_id in this wave.",
        "task_c_handling": "Record as an explicit unsupported parity gap; do not widen Task C into a runtime semantic edit.",
    },
    {
        "gap_id": "claude_taskstop_projection",
        "difference_kind": "unsupported_capability",
        "source_paths": [
            CLAUDE_REFERENCE_FILES[0],
            CLAUDE_REFERENCE_FILES[4],
            CLAUDE_REFERENCE_FILES[5],
        ],
        "reference_behavior": "Claude exposes Agent plus SendMessage and generic TaskStop(task_id) for stoppable background work.",
        "agenthub_current_behavior": "AgentHub claude_code projection intentionally exposes Agent plus SendMessage only; no TaskStop parity surface exists.",
        "task_c_handling": "Treat stop/close parity on the Claude lane as conditional or unsupported instead of inventing a fake close tool.",
    },
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _host_platform() -> HostPlatform:
    return HostPlatform(
        family="unix",
        os="linux",
        shell_kind="bash",
        shell_program="/bin/bash",
        list_dir_command="ls -la",
        print_working_dir_command="pwd",
        python_version_command="python -V",
    )


def _agenthub_config(profile: str) -> ProviderConfig:
    normalized = str(profile or "").strip()
    if normalized == "claude_code":
        return ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile=normalized,
            interaction_profile_source="spawn_agent_wave02_acceptance",
        )
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="responses",
        interaction_profile=normalized,
        interaction_profile_source="spawn_agent_wave02_acceptance",
    )


def _agenthub_profile_snippet(profile: str) -> str:
    return "\n".join(
        [
            'model_provider = "openai"',
            'model = "gpt-5.4"',
            "",
            "[model_providers.openai]",
            'base_url = "https://api.openai.com/v1"',
            'wire_api = "responses"',
            'default_model = "gpt-5.4"',
            'api_key_env = "OPENAI_API_KEY"',
            "",
            '[models."gpt-5.4"]',
            'provider = "openai"',
            'model_id = "gpt-5.4"',
            'planner_kind = "openai_responses"',
            'wire_api = "responses"',
            'reasoning_effort = "high"',
            f'interaction_profile = "{profile}"',
        ]
    )


def _agenthub_surface_snapshot(profile: str) -> dict[str, Any]:
    config = _agenthub_config(profile)
    visible_names = provider_tool_names(config, _host_platform())
    delegation_surface = [name for name in visible_names if name in RELEVANT_DELEGATION_NAMES]
    ordered_expectation = list(visible_delegation_tool_order(tool_surface_profile=profile))
    ordered_surface = [name for name in delegation_surface if name in ordered_expectation]
    return {
        "system": "agenthub",
        "lane_id": f"agenthub_{profile}",
        "interaction_profile": profile,
        "delegation_tool_surface": ordered_surface,
        "surface_source": "cli.agent_cli.providers.tool_specs.provider_tool_names",
        "config_snippet": _agenthub_profile_snippet(profile),
    }


def _reference_surface_snapshot(lane_id: str) -> dict[str, Any]:
    if lane_id == "codex_ref":
        return {
            "system": "codex_ref",
            "lane_id": lane_id,
            "delegation_tool_surface": [
                "spawn_agent",
                "send_input",
                "resume_agent",
                "wait",
                "close_agent",
            ],
            "reference_paths": list(CODEX_REFERENCE_FILES),
            "notes": [
                "wait is a first-class visible tool and accepts ids[].",
                "Batch collaboration helpers exist in Codex but remain out of scope for this wave.",
            ],
        }
    return {
        "system": "claude_code_ref",
        "lane_id": lane_id,
        "delegation_tool_surface": [
            "Agent",
            "SendMessage",
            "TaskStop",
        ],
        "reference_paths": list(CLAUDE_REFERENCE_FILES),
        "notes": [
            "Agent is the primary spawn surface.",
            "Background completion is notification-driven; there is no model-visible wait or resume_agent tool.",
        ],
    }


def _surface_matrix() -> list[dict[str, Any]]:
    return [
        _agenthub_surface_snapshot("codex_openai"),
        _agenthub_surface_snapshot("claude_code"),
        _agenthub_surface_snapshot("generic_chat"),
        _reference_surface_snapshot("codex_ref"),
        _reference_surface_snapshot("claude_code_ref"),
    ]


StepSpec = spawn_agent_wave02_case_specs_runtime_service.StepSpec
CaseSpec = spawn_agent_wave02_case_specs_runtime_service.CaseSpec


def _case_specs() -> tuple[CaseSpec, ...]:
    return spawn_agent_wave02_case_specs_runtime_service.case_specs(
        task_b_blocked_assumptions=TASK_B_BLOCKED_ASSUMPTIONS
    )


def _selected_cases(case_ids: list[str] | None) -> list[CaseSpec]:
    return spawn_agent_wave02_case_specs_runtime_service.selected_cases(
        case_ids,
        case_specs_fn=_case_specs,
    )


def _selected_lanes(lane_ids: list[str] | None) -> list[str]:
    return spawn_agent_wave02_case_specs_runtime_service.selected_lanes(
        lane_ids,
        all_lanes=ALL_LANES,
    )


def _case_lane_payload(
    case: CaseSpec,
    lane_id: str,
    *,
    dry_run: bool,
    sandbox_mode: str,
    approval_policy: str,
) -> dict[str, Any]:
    return spawn_agent_wave02_report_runtime_service.case_lane_payload(
        case,
        lane_id,
        dry_run=dry_run,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        default_agenthub_main=DEFAULT_AGENTHUB_MAIN,
    )


def _case_report(
    case: CaseSpec,
    *,
    lane_ids: list[str],
    dry_run: bool,
    sandbox_mode: str,
    approval_policy: str,
) -> dict[str, Any]:
    return spawn_agent_wave02_report_runtime_service.case_report(
        case,
        lane_ids=lane_ids,
        dry_run=dry_run,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        default_agenthub_main=DEFAULT_AGENTHUB_MAIN,
    )


def _markdown_report(report: dict[str, Any]) -> str:
    return spawn_agent_wave02_report_runtime_service.markdown_report(report)
