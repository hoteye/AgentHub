from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from cli.scripts.request_user_input_bridged_openai_ab_projection_helpers import (
        _completed_status,
        _final_answer_summary,
        _parity_verdict,
        _public_request_shape,
        _turn_completion_outcome,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_runtime_helpers import ProbeResult
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from request_user_input_bridged_openai_ab_projection_helpers import (  # type: ignore[no-redef]
        _completed_status,
        _final_answer_summary,
        _parity_verdict,
        _public_request_shape,
        _turn_completion_outcome,
    )
    from request_user_input_bridged_openai_ab_runtime_helpers import ProbeResult  # type: ignore[no-redef]


def build_summary(
    agenthub: ProbeResult,
    codex: ProbeResult,
    *,
    prompt: str,
    answer: str,
    base_url: str,
    model: str,
    effort: str,
) -> dict[str, Any]:
    turn_completion_outcome = _turn_completion_outcome(agenthub, codex)
    parity_verdict = _parity_verdict(agenthub, codex)
    return {
        "prompt": prompt,
        "answer": answer,
        "base_url": base_url,
        "model": model,
        "effort": effort,
        "agenthub": {
            "request_user_input": _public_request_shape(agenthub.request_user_input_message),
            "server_request_resolved": agenthub.resolved_message,
            "final_answer": _final_answer_summary(agenthub.final_answer_message),
            "turn_completed": _completed_status(agenthub.completed_message),
            "transcript_path": str(agenthub.transcript_path),
            "stderr_path": str(agenthub.stderr_path),
            "tmp_root": str(agenthub.tmp_root),
            "transcript_line_count": len(agenthub.transcript),
        },
        "codex": {
            "request_user_input": _public_request_shape(codex.request_user_input_message),
            "server_request_resolved": codex.resolved_message,
            "final_answer": _final_answer_summary(codex.final_answer_message),
            "turn_completed": _completed_status(codex.completed_message),
            "transcript_path": str(codex.transcript_path),
            "stderr_path": str(codex.stderr_path),
            "tmp_root": str(codex.tmp_root),
            "transcript_line_count": len(codex.transcript),
        },
        "comparison": {
            "both_emitted_request_user_input": bool(agenthub.request_user_input_message and codex.request_user_input_message),
            "both_emitted_server_request_resolved": bool(agenthub.resolved_message and codex.resolved_message),
            "both_emitted_final_answer": bool(agenthub.final_answer_message and codex.final_answer_message),
            "both_completed": _completed_status(agenthub.completed_message).get("status") == "completed"
            and _completed_status(codex.completed_message).get("status") == "completed",
            "turn_completion_outcome": turn_completion_outcome,
            "live_close_bucket": (
                "stable_completion" if turn_completion_outcome == "both_completed" else "live_close_instability_observed"
            ),
            "parity_verdict": parity_verdict["code"],
            "parity_reason": parity_verdict["reason"],
        },
    }


def build_aggregate_summary(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    verdict_counts = Counter()
    outcome_counts = Counter()
    for summary in run_summaries:
        comparison = dict(summary.get("comparison") or {})
        verdict_counts[str(comparison.get("parity_verdict") or "unknown")] += 1
        outcome_counts[str(comparison.get("turn_completion_outcome") or "unknown")] += 1
    return {
        "total_runs": len(run_summaries),
        "verdict_counts": dict(verdict_counts),
        "turn_completion_outcome_counts": dict(outcome_counts),
        "overall_verdict": (
            "pass"
            if verdict_counts == Counter({"pass": len(run_summaries)})
            else (
                "shared_live_instability"
                if verdict_counts.get("inconclusive_live_close_instability", 0) > 0
                else "contract_or_bridge_gap"
            )
        ),
        "overall_reason": (
            "All runs completed on both AgentHub and codex_ref."
            if verdict_counts == Counter({"pass": len(run_summaries)})
            else (
                "At least one run observed final-answer close instability; do not attribute product regression from this aggregate alone."
                if verdict_counts.get("inconclusive_live_close_instability", 0) > 0
                else "At least one run diverged before stable shared final-answer behavior; inspect contract or bridge behavior."
            )
        ),
    }
