from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from cli.agent_cli.acceptance_support.spawn_agent_wave02_case_specs_runtime import CaseSpec, StepSpec


def lane_command_template(
    lane_id: str,
    prompt: str,
    *,
    default_agenthub_main: Path,
    sandbox_mode: str,
    approval_policy: str,
) -> str:
    quoted_prompt = shlex.quote(prompt)
    if lane_id.startswith("agenthub_"):
        profile = lane_id.removeprefix("agenthub_")
        return (
            f"python {shlex.quote(str(default_agenthub_main))} "
            f"--headless --json --approval-policy {approval_policy} "
            f"--sandbox-mode {sandbox_mode} "
            f"--prompt {quoted_prompt} "
            f'# run from a workspace whose .config/config.toml sets interaction_profile = "{profile}"'
        )
    if lane_id == "codex_ref":
        return (
            "codex exec --json --skip-git-repo-check "
            f"--sandbox {sandbox_mode} "
            f"{quoted_prompt}"
        )
    return (
        "claude -p --output-format json "
        "--permission-mode acceptEdits "
        f"{quoted_prompt}"
    )


def unsupported_lane(
    *,
    lane_id: str,
    reason: str,
    difference_kind: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "supported": False,
        "difference_kind": difference_kind,
        "run": {
            "skipped": True,
            "skip_reason": "unsupported_path",
            "dry_run": bool(dry_run),
        },
        "outcome_classification": {
            "classification": "unsupported",
            "reason": reason,
            "inferred": False,
        },
        "steps": [],
        "supported_conclusions": [],
        "unsupported_conclusions": [reason],
        "blocked_assumptions": [],
    }


def supported_lane(
    *,
    lane_id: str,
    steps: tuple[StepSpec, ...],
    dry_run: bool,
    sandbox_mode: str,
    approval_policy: str,
    blocked_assumptions: tuple[str, ...],
    default_agenthub_main: Path,
) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "supported": True,
        "difference_kind": "",
        "run": {
            "skipped": True,
            "skip_reason": "dry_run" if dry_run else "operator_live_run_required",
            "dry_run": bool(dry_run),
        },
        "outcome_classification": {
            "classification": "not_run",
            "reason": "dry_run" if dry_run else "operator_live_run_required",
            "inferred": False,
        },
        "steps": [
            {
                "step_id": step.step_id,
                "title": step.title,
                "prompt": step.prompt,
                "command_template": lane_command_template(
                    lane_id,
                    step.prompt,
                    default_agenthub_main=default_agenthub_main,
                    sandbox_mode=sandbox_mode,
                    approval_policy=approval_policy,
                ),
                "expected_visible_tools": list(step.expected_visible_tools),
                "evidence_expectations": list(step.evidence_expectations),
                "lifecycle_expectations": list(step.lifecycle_expectations),
                "result_contract_expectations": list(step.result_contract_expectations),
                "notes": list(step.notes),
            }
            for step in steps
        ],
        "supported_conclusions": [],
        "unsupported_conclusions": [],
        "blocked_assumptions": list(blocked_assumptions),
    }


def case_lane_payload(
    case: CaseSpec,
    lane_id: str,
    *,
    dry_run: bool,
    sandbox_mode: str,
    approval_policy: str,
    default_agenthub_main: Path,
) -> dict[str, Any]:
    if case.case_id == "case_d_stop_or_close_surface" and lane_id == "agenthub_claude_code":
        return unsupported_lane(
            lane_id=lane_id,
            reason="AgentHub claude_code exposes no TaskStop or close_agent parity surface for this stop/close case.",
            difference_kind="unsupported_capability",
            dry_run=dry_run,
        )
    if case.case_id == "case_e_agenthub_control_plane" and lane_id in {
        "codex_ref",
        "claude_code_ref",
        "agenthub_codex_openai",
        "agenthub_claude_code",
    }:
        return unsupported_lane(
            lane_id=lane_id,
            reason="agent_workflow and recover_agent are AgentHub-only control-plane evidence and are intentionally not parity targets here.",
            difference_kind="projection_or_policy_difference" if lane_id.startswith("agenthub_") else "unsupported_capability",
            dry_run=dry_run,
        )
    if lane_id not in case.supported_lanes:
        return unsupported_lane(
            lane_id=lane_id,
            reason="This lane is not part of the source-backed acceptance target for the selected case.",
            difference_kind="projection_or_policy_difference",
            dry_run=dry_run,
        )
    return supported_lane(
        lane_id=lane_id,
        steps=case.steps_by_lane[lane_id],
        dry_run=dry_run,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        blocked_assumptions=case.blocked_assumptions,
        default_agenthub_main=default_agenthub_main,
    )


def case_report(
    case: CaseSpec,
    *,
    lane_ids: list[str],
    dry_run: bool,
    sandbox_mode: str,
    approval_policy: str,
    default_agenthub_main: Path,
) -> dict[str, Any]:
    lanes = [
        case_lane_payload(
            case,
            lane_id,
            dry_run=dry_run,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            default_agenthub_main=default_agenthub_main,
        )
        for lane_id in lane_ids
    ]
    return {
        "case_id": case.case_id,
        "title": case.title,
        "family": case.family,
        "comparison_labels": list(case.comparison_labels),
        "supported_conclusions": list(case.supported_conclusions),
        "unsupported_conclusions": list(case.unsupported_conclusions),
        "blocked_assumptions": list(case.blocked_assumptions),
        "lanes": lanes,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Spawn Agent Wave 02 live cross-system acceptance bundle")
    lines.append("")
    lines.append("## Test Method")
    lines.append("")
    run_conditions = dict(report.get("run_conditions") or {})
    lines.append(f"- dry_run: `{str(report.get('dry_run')).lower()}`")
    lines.append(f"- workspace_root: `{run_conditions.get('workspace_root')}`")
    lines.append(f"- sandbox_mode: `{run_conditions.get('sandbox_mode')}`")
    lines.append(f"- approval_policy: `{run_conditions.get('approval_policy')}`")
    lines.append(f"- selected_cases: `{', '.join(report.get('selected_cases') or [])}`")
    lines.append(f"- selected_lanes: `{', '.join(report.get('selected_lanes') or [])}`")
    lines.append("")
    lines.append("## Reference Anchors")
    lines.append("")
    lines.append("### codex_ref")
    for path in report["reference_files"]["codex_ref"]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("### claude_code_ref")
    for path in report["reference_files"]["claude_code_ref"]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Difference Taxonomy")
    lines.append("")
    for item in report.get("difference_taxonomy") or []:
        lines.append(f"- `{item['kind']}`: {item['definition']}")
    lines.append("")
    lines.append("## AgentHub Surface Snapshot")
    lines.append("")
    for row in report.get("surface_matrix") or []:
        lines.append(f"### {row['lane_id']}")
        lines.append(f"- system: `{row['system']}`")
        if row.get("interaction_profile"):
            lines.append(f"- interaction_profile: `{row['interaction_profile']}`")
        lines.append(f"- delegation_tool_surface: `{', '.join(row.get('delegation_tool_surface') or [])}`")
        if row.get("notes"):
            for note in row.get("notes") or []:
                lines.append(f"- note: {note}")
        lines.append("")
    lines.append("## Parity Gaps")
    lines.append("")
    for item in report.get("parity_gap_notes") or []:
        lines.append(f"### {item['gap_id']}")
        lines.append(f"- difference_kind: `{item['difference_kind']}`")
        lines.append(f"- reference_behavior: {item['reference_behavior']}")
        lines.append(f"- agenthub_current_behavior: {item['agenthub_current_behavior']}")
        lines.append(f"- task_c_handling: {item['task_c_handling']}")
        lines.append("")
    lines.append("## Case Matrix")
    lines.append("")
    for case in report.get("cases") or []:
        lines.append(f"### {case['case_id']}")
        lines.append(f"- title: {case['title']}")
        lines.append(f"- family: `{case['family']}`")
        lines.append(f"- comparison_labels: `{', '.join(case.get('comparison_labels') or [])}`")
        if case.get("blocked_assumptions"):
            lines.append("- blocked_assumptions:")
            for item in case.get("blocked_assumptions") or []:
                lines.append(f"  - {item}")
        for lane in case.get("lanes") or []:
            lines.append(f"- lane `{lane['lane_id']}`:")
            lines.append(
                f"  - outcome: `{lane['outcome_classification']['classification']}` ({lane['outcome_classification']['reason']})"
            )
            if lane.get("supported"):
                for step in lane.get("steps") or []:
                    lines.append(f"  - step `{step['step_id']}`: {step['title']}")
                    lines.append(f"    - expected_visible_tools: `{', '.join(step.get('expected_visible_tools') or [])}`")
                    lines.append(f"    - prompt: {step['prompt']}")
                    lines.append(f"    - command_template: `{step['command_template']}`")
                    if step.get("evidence_expectations"):
                        lines.append(f"    - evidence: `{'; '.join(step.get('evidence_expectations') or [])}`")
                    if step.get("result_contract_expectations"):
                        lines.append("    - result_contract: " f"`{'; '.join(step.get('result_contract_expectations') or [])}`")
            else:
                for item in lane.get("unsupported_conclusions") or []:
                    lines.append(f"  - unsupported: {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "case_lane_payload",
    "case_report",
    "lane_command_template",
    "markdown_report",
    "supported_lane",
    "unsupported_lane",
]
