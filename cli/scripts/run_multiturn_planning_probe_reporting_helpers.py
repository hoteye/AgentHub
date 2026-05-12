from __future__ import annotations

from typing import Any


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AgentHub Multi-Turn Planning Probe",
        "",
        "## Scope",
        "",
        "- system: AgentHub headless serve",
        f"- provider: {report.get('provider')}",
        f"- model: {report.get('model')}",
        f"- reasoning_effort: {report.get('reasoning_effort')}",
        f"- interaction_profile: {report.get('interaction_profile')}",
        f"- generated_at: {report.get('generated_at')}",
        "",
        "## Results",
        "",
        "| Case | Result | Plan Turns | Replan | Validation | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case_result in list(report.get("cases") or []):
        evaluation = dict(case_result.get("evaluation") or {})
        notes = "; ".join(str(item) for item in list(evaluation.get("issues") or [])[:2]) or "-"
        validation_results = list(evaluation.get("validation_results") or [])
        if not validation_results:
            validation_label = "-"
        else:
            validation_label = (
                "ok"
                if all(int(item.get("returncode") or 0) == 0 for item in validation_results)
                else "failed"
            )
        lines.append(
            "| {name} | {result} | {plan_turns} | {replan} | {validation} | {notes} |".format(
                name=case_result.get("case_name"),
                result="PASS" if evaluation.get("passed") else "FAIL",
                plan_turns=",".join(str(item) for item in list(evaluation.get("plan_turns") or [])) or "-",
                replan="yes" if evaluation.get("replan_detected") else "no",
                validation=validation_label,
                notes=notes.replace("\n", " "),
            )
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- report.json: `{report.get('report_path')}`",
        ]
    )
    for case_result in list(report.get("cases") or []):
        lines.append(f"- {case_result.get('case_name')}: `{case_result.get('attempt_root')}`")
    return "\n".join(lines).strip() + "\n"
