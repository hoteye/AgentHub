from __future__ import annotations

from typing import Any

from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime


def review_projection_state(
    *,
    result_state: Any,
    completion_state: Any,
    final_apply_state: Any,
) -> str:
    return operator_runtime.operator_review_state(
        result_state=result_state,
        completion_state=completion_state,
        final_apply_state=final_apply_state,
    )


def orchestration_next_command(
    *,
    run_id: str,
    card_id: str,
    review_action: str,
    phase: str,
    workflow_state: str,
) -> str:
    action = str(review_action or "").strip().lower()
    phase_text = str(phase or "").strip().lower()
    workflow_text = str(workflow_state or "").strip().lower()
    if action in {"apply", "accept"} and run_id and card_id:
        return f"/orchestrate_apply {run_id} {card_id}"
    if action in {"reject", "block", "rework"} and run_id and card_id:
        return f"/orchestrate_reject {run_id} {card_id}"
    if action in {"continue", "resume", "dispatch"} and run_id:
        return f"/orchestrate_continue {run_id}"
    if run_id and card_id and any(token in phase_text for token in ("review", "pending")):
        return f"/orchestrate_apply {run_id} {card_id}"
    if run_id and workflow_text in {"blocked", "review"}:
        return f"/orchestrate_progress {run_id}"
    if run_id:
        return f"/orchestrate_continue {run_id}"
    return ""
