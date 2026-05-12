from __future__ import annotations

from typing import Any

from cli.scripts.apply_patch_wave01_acceptance_case_helpers import DEFAULT_CASES
from cli.scripts.apply_patch_wave01_acceptance_model_helpers import CaseSpec


def _selected_cases(case_filters: list[str]) -> list[CaseSpec]:
    if not case_filters:
        return list(DEFAULT_CASES)
    wanted = {text.strip() for text in case_filters if text.strip()}
    selected = [case for case in DEFAULT_CASES if case.case_id in wanted]
    if not selected:
        raise SystemExit(f"no matching cases for --case: {sorted(wanted)}")
    return selected


def _markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 20260416 Apply Patch Wave 01 Acceptance Bundle\n\n")
    lines.append("## Scope\n\n")
    lines.append("- This bundle validates the TASK A + TASK C state only.\n")
    lines.append("- TASK B provider-visible surface/prompt closure remains pending and is not claimed complete here.\n")
    lines.append("- Harness: `cli/scripts/apply_patch_wave01_acceptance.py`\n")
    lines.append(f"- generated_at: {report.get('generated_at')}\n")
    lines.append(f"- out_dir: `{report.get('out_dir')}`\n")
    lines.append("\n## AgentHub Surface Snapshot\n\n")
    lines.append("| profile | model | relevant tools | apply_patch | Write | Edit |\n")
    lines.append("| --- | --- | --- | --- | --- | --- |\n")
    for item in list(report.get("surface_matrix") or []):
        lines.append(
            "| {profile} | {model} | {tools} | {apply_patch} | {write} | {edit} |".format(
                profile=item.get("profile"),
                model=item.get("model"),
                tools=", ".join(item.get("relevant_tool_names") or []),
                apply_patch="yes" if item.get("has_apply_patch") else "no",
                write="yes" if item.get("has_write") else "no",
                edit="yes" if item.get("has_edit") else "no",
            )
        )
    lines.append("\n## Reference Systems\n\n")
    for item in list(report.get("reference_systems") or []):
        lines.append(f"### {item.get('system')}\n\n")
        lines.append(f"- model_visible_tools: {item.get('model_visible_tools')}\n")
        lines.append("- reference_files:\n")
        for path in list(item.get("reference_files") or []):
            lines.append(f"  - `{path}`")
        lines.append("- notes:\n")
        for note in list(item.get("notes") or []):
            lines.append(f"  - {note}")
        lines.append("")
    lines.append("## Case Summary\n\n")
    lines.append("| case | family | result |\n")
    lines.append("| --- | --- | --- |\n")
    for case in list(report.get("cases") or []):
        lines.append(
            "| {case_id} | {family} | {result} |".format(
                case_id=case.get("case_id"),
                family=case.get("family"),
                result="PASS" if case.get("passed") else "FAIL",
            )
        )
    lines.append("")
    for case in list(report.get("cases") or []):
        lines.append(f"### {case.get('case_id')}\n\n")
        lines.append(f"- family: `{case.get('family')}`\n")
        lines.append(f"- description: {case.get('description')}\n")
        lines.append(f"- passed: {case.get('passed')}\n")
        if case.get("error"):
            lines.append(f"- error: `{case.get('error')}`\n")
        lines.append("- steps:\n")
        for step in list(case.get("steps") or []):
            completed = [item.get("name") for item in list(step.get("completed_items") or []) if item.get("name")]
            lines.append(
                f"  - {step.get('step')}: tool_events={step.get('tool_event_names')} completed_items={completed} activities={step.get('activity_titles')}"
            )
        lines.append("- file_results:\n")
        for item in list(case.get("file_results") or []):
            lines.append(
                f"  - {item.get('path')}: ok={item.get('ok')} expected={item.get('expected')!r} actual={item.get('actual')!r}"
            )
        lines.append("")
    lines.append("## Regression Bundle\n\n")
    for label, commands in dict(report.get("regression_bundle") or {}).items():
        lines.append(f"### {label}\n\n")
        for command in list(commands or []):
            lines.append(f"- `{command}`")
        lines.append("")
    lines.append("## Open Gaps\n\n")
    for gap in list(report.get("open_gaps") or []):
        lines.append(f"- {gap}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
