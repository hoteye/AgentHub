from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.acceptance_support.web_search_wave02_support_pure_helpers import (
    CommandResult,
    PromptFamily,
    _case_request_contract_deltas,
    _effective_web_search_mode_for_turn,
    _external_web_access_for_turn,
    _to_int,
)


def build_supported_conclusions(case: PromptFamily, systems: list[dict[str, Any]]) -> list[str]:
    by_system = {str(item.get("system") or ""): item for item in systems}
    supported: list[str] = []
    agenthub = by_system.get("agenthub", {})
    codex = by_system.get("codex", {})
    claude = by_system.get("claude", {})
    agenthub_class = str(((agenthub.get("outcome_classification") or {}).get("classification")) or "").strip()
    codex_class = str(((codex.get("outcome_classification") or {}).get("classification")) or "").strip()
    claude_class = str(((claude.get("outcome_classification") or {}).get("classification")) or "").strip()
    if agenthub.get("answer_quality", {}).get("passed"):
        supported.append(f"AgentHub reached `{agenthub_class or 'completed'}` for this prompt family.")
    if codex.get("answer_quality", {}).get("passed"):
        supported.append(f"Codex reached `{codex_class or 'completed'}` for the same prompt family.")
    if (
        agenthub_class == "native_complete"
        and codex_class == "native_complete"
        and bool((((agenthub.get("parity_evidence") or {}).get("codex_comparable") or {}).get("web_search_call_seen")))
        and bool((((codex.get("parity_evidence") or {}).get("codex_comparable") or {}).get("web_search_call_seen")))
    ):
        supported.append(
            "AgentHub and Codex both exposed Codex-comparable `web_search_call` evidence under the same bundle contract."
        )
    if claude_class == "server_tool_complete" and _to_int(
        (((claude.get("parity_evidence") or {}).get("claude_comparable") or {}).get("web_search_requests"))
    ) > 0:
        supported.append(
            "Claude-style lane exposed first-class web-search accounting through `usage.server_tool_use.web_search_requests`."
        )
    return supported


def build_unsupported_conclusions(
    case: PromptFamily,
    systems: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[str]:
    by_system = {str(item.get("system") or ""): item for item in systems}
    unsupported: list[str] = []
    if bool(args.dry_run):
        unsupported.append(
            "Dry-run output only validates harness structure and report shape; it does not support live provider parity conclusions."
        )
    if not by_system.get("agenthub", {}).get("answer_quality", {}).get("passed"):
        unsupported.append("AgentHub answer quality was insufficient for pass-level parity claims on this case.")
    if "codex" in case.applicability and not by_system.get("codex", {}).get("answer_quality", {}).get("passed"):
        unsupported.append("Codex did not produce a pass-level answer for this case, so Codex parity remains unsupported here.")
    if "claude" not in case.applicability:
        unsupported.append("Claude-style comparison is intentionally out of scope for this case.")
    else:
        claude = by_system.get("claude", {})
        if bool(claude.get("run", {}).get("skipped")):
            unsupported.append("Claude-style lane was skipped in this run, so no live Claude conclusion is supported.")
        elif not bool((((claude.get("parity_evidence") or {}).get("claude_comparable") or {}).get("raw_block_markers_available"))):
            unsupported.append(
                "Claude CLI JSON did not expose raw `server_tool_use` / `web_search_tool_result` pairing; only usage-counter evidence is available."
            )
    if "common-three-way" in case.comparison_labels:
        agenthub_ok = by_system.get("agenthub", {}).get("answer_quality", {}).get("passed")
        codex_ok = by_system.get("codex", {}).get("answer_quality", {}).get("passed")
        claude_ok = by_system.get("claude", {}).get("answer_quality", {}).get("passed")
        if not (agenthub_ok and codex_ok and claude_ok):
            unsupported.append("Three-way parity is not established for this case from the current evidence bundle.")
    return unsupported


def build_provider_instability_notes(systems: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for system in systems:
        system_name = str(system.get("system") or "").strip()
        run = dict(system.get("run") or {})
        outcome = dict(system.get("outcome_classification") or {})
        classification = str(outcome.get("classification") or "").strip()
        if bool(run.get("timed_out")):
            notes.append(f"{system_name}: command timed out before a stable conclusion was available.")
        if classification in {"native_degraded", "server_tool_interrupted", "fallback_error", "provider_error_without_search"}:
            notes.append(f"{system_name}: {classification} ({str(outcome.get('reason') or '').strip()}).")
        if system_name == "claude" and not bool(run.get("skipped")) and not bool(
            (((system.get("parity_evidence") or {}).get("claude_comparable") or {}).get("raw_block_markers_available"))
        ):
            notes.append(
                "claude: raw server-tool blocks were not exposed by CLI JSON output; only usage-counter evidence was observable."
            )
    return notes


def build_case_report(
    case: PromptFamily,
    systems: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    provider_instability_notes_fn: Callable[[list[dict[str, Any]]], list[str]],
    supported_conclusions_fn: Callable[[PromptFamily, list[dict[str, Any]]], list[str]],
    unsupported_conclusions_fn: Callable[[PromptFamily, list[dict[str, Any]], argparse.Namespace], list[str]],
) -> dict[str, Any]:
    by_system = {str(item.get("system") or ""): item for item in systems}
    return {
        "case_id": case.case_id,
        "family": case.family,
        "prompt": case.prompt,
        "comparison_labels": list(case.comparison_labels),
        "evidence_basis": "live",
        "request_side_variables": {
            "reasoning_effort": str(args.reasoning_effort),
            "web_search_mode": str(args.web_search_mode),
            "sandbox_mode": str(args.sandbox_mode),
            "effective_web_search_mode": _effective_web_search_mode_for_turn(args.web_search_mode, args.sandbox_mode),
            "external_web_access": _external_web_access_for_turn(args.web_search_mode, args.sandbox_mode),
        },
        "request_contract_deltas": _case_request_contract_deltas(case),
        "systems": systems,
        "provider_instability_notes": provider_instability_notes_fn(systems),
        "supported_conclusions": supported_conclusions_fn(case, systems),
        "unsupported_conclusions": unsupported_conclusions_fn(case, systems, args),
        "matrix_summary": {
            "agenthub": str(((by_system.get("agenthub") or {}).get("outcome_classification") or {}).get("classification") or "").strip(),
            "codex": str(((by_system.get("codex") or {}).get("outcome_classification") or {}).get("classification") or "").strip(),
            "claude": str(((by_system.get("claude") or {}).get("outcome_classification") or {}).get("classification") or "").strip(),
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 20260416 Web Search Live Acceptance Bundle\n\n")
    lines.append("## Test Method\n\n")
    lines.append("- harness: `cli/scripts/web_search_wave02_acceptance.py`\n")
    lines.append(f"- contract_version: `{report.get('contract_version')}`\n")
    lines.append(f"- generated_at: {report.get('generated_at')}\n")
    lines.append(f"- out_dir: `{report.get('out_dir')}`\n")
    lines.append(f"- provider: `{report.get('provider')}`\n")
    lines.append(f"- model: `{report.get('model')}`\n")
    lines.append(f"- reasoning_effort: `{report.get('reasoning_effort')}`\n")
    lines.append(f"- web_search_mode: `{report.get('web_search_mode')}`\n")
    lines.append(f"- dry_run: `{report.get('dry_run')}`\n")
    lines.append("\n## Cases\n\n")
    for case in list(report.get("cases") or []):
        lines.append(f"### {case.get('case_id')}\n\n")
        lines.append(f"- family: `{case.get('family')}`\n")
        lines.append(f"- comparison_labels: `{', '.join(case.get('comparison_labels') or [])}`\n")
        lines.append(f"- evidence_basis: `{case.get('evidence_basis')}`\n")
        lines.append(f"- prompt: {case.get('prompt')}\n")
        lines.append(
            f"- request_side_variables: `{json.dumps(case.get('request_side_variables') or {}, ensure_ascii=False, sort_keys=True)}`\n"
        )
        lines.append("- request_contract_deltas:\n")
        for item in list(case.get("request_contract_deltas") or []):
            lines.append(f"  - {item}")
        lines.append("- request/run conditions:\n")
        for system in list(case.get("systems") or []):
            run = dict(system.get("run") or {})
            lines.append(
                f"  - {system.get('system')}: exit={run.get('exit_code')} timed_out={run.get('timed_out')} skipped={run.get('skipped')}"
            )
        lines.append("- request contract by system:\n")
        for system in list(case.get("systems") or []):
            contract = dict(system.get("request_contract") or {})
            lines.append(f"  - {system.get('system')}: `{json.dumps(contract, ensure_ascii=False, sort_keys=True)}`")
        lines.append("- observable execution path:\n")
        for system in list(case.get("systems") or []):
            path = dict(system.get("observable_execution_path") or {})
            lines.append(f"  - {system.get('system')}: `{json.dumps(path, ensure_ascii=False, sort_keys=True)}`")
        lines.append("- parity evidence:\n")
        for system in list(case.get("systems") or []):
            evidence = dict(system.get("parity_evidence") or {})
            lines.append(f"  - {system.get('system')}: `{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}`")
        lines.append("- outcome classification:\n")
        for system in list(case.get("systems") or []):
            outcome = dict(system.get("outcome_classification") or {})
            lines.append(f"  - {system.get('system')}: `{json.dumps(outcome, ensure_ascii=False, sort_keys=True)}`")
        lines.append("- final answer quality:\n")
        for system in list(case.get("systems") or []):
            quality = dict(system.get("answer_quality") or {})
            lines.append(f"  - {system.get('system')}: passed={quality.get('passed')} preview={quality.get('preview')!r}")
        lines.append("- provider instability notes:\n")
        for item in list(case.get("provider_instability_notes") or []):
            lines.append(f"  - {item}")
        lines.append("- supported conclusions:\n")
        for item in list(case.get("supported_conclusions") or []):
            lines.append(f"  - {item}")
        lines.append("- unsupported conclusions:\n")
        for item in list(case.get("unsupported_conclusions") or []):
            lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_case_system_summary(
    *,
    system: str,
    case: PromptFamily,
    detail: dict[str, Any],
    result: CommandResult,
    args: argparse.Namespace,
    detail_path: Path,
    parity_evidence_fn: Callable[[str, dict[str, Any], argparse.Namespace], dict[str, Any]],
    answer_quality_fn: Callable[[PromptFamily, str], dict[str, Any]],
    request_contract_fn: Callable[[str, argparse.Namespace, dict[str, Any]], dict[str, Any]],
    observable_execution_path_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
    outcome_classification_fn: Callable[..., dict[str, Any]],
    write_json_fn: Callable[[Path, Any], None],
) -> dict[str, Any]:
    assistant_text = str(detail.get("assistant_text") or "").strip()
    parity_evidence = parity_evidence_fn(system, detail, args)
    answer_quality = answer_quality_fn(case, assistant_text)
    run_dict = asdict(result)
    summary = {
        "system": system,
        "run": run_dict,
        "request_contract": request_contract_fn(system, args, parity_evidence),
        "observable_execution_path": observable_execution_path_fn(system, parity_evidence),
        "parity_evidence": parity_evidence,
        "answer_quality": answer_quality,
        "assistant_text": assistant_text,
        "outcome_classification": outcome_classification_fn(
            system,
            run=run_dict,
            answer_quality=answer_quality,
            parity_evidence=parity_evidence,
        ),
        "detail_path": str(detail_path),
    }
    write_json_fn(detail_path, detail)
    return summary


__all__ = [
    "build_case_report",
    "build_case_system_summary",
    "build_provider_instability_notes",
    "build_supported_conclusions",
    "build_unsupported_conclusions",
    "render_markdown_report",
]
