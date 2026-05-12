from __future__ import annotations

from typing import Any


def _render_summary(report: dict[str, Any]) -> str:
    lines = [
        "# AgentHub vs Codex Multi-Turn Planning A/B",
        "",
        "## Scope",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- agenthub_provider: {report.get('agenthub_provider')}",
        f"- agenthub_model: {report.get('agenthub_model')}",
        f"- reasoning_effort: {report.get('reasoning_effort')}",
        "",
        "## Case Results",
        "",
        "| Case | AgentHub | Codex | Planning Diff | Validation Diff |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in list(report.get("cases") or []):
        agenthub = case["systems"]["agenthub"]["evaluation"]
        codex = case["systems"]["codex"]["evaluation"]
        planning_diff = (
            f"AH turns {agenthub.get('plan_turns') or []} vs Codex turns {codex.get('plan_turns') or []}"
        )
        validation_diff = (
            f"AH issues={agenthub.get('issues') or []}; Codex issues={codex.get('issues') or []}"
        )
        lines.append(
            "| {name} | {ah} | {cx} | {planning} | {validation} |".format(
                name=case.get("case_name"),
                ah="PASS" if agenthub.get("passed") else "FAIL",
                cx="PASS" if codex.get("passed") else "FAIL",
                planning=planning_diff.replace("\n", " "),
                validation=validation_diff.replace("\n", " "),
            )
        )
    return "\n".join(lines).rstrip() + "\n"
