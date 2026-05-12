from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRunStatus, TaskCardState

from .taskbook_runtime_support_runtime import extend_unique, progress_payload_mutated


def payload_card_ids(payload: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in list(payload.get(key) or []) if str(item or "").strip()]


def defer_progress_auto_dispatch(state: TaskCardState | None) -> bool:
    if not isinstance(state, TaskCardState):
        return False
    scheduler_decision = str(state.last_scheduler_decision or "").strip()
    return scheduler_decision in {"rework_requested_by_acceptance"}


def continue_pass_summary(pass_index: int, payload: dict[str, Any]) -> dict[str, Any]:
    synced_cards = payload_card_ids(payload, "synced_card_ids")
    accepted_cards = payload_card_ids(payload, "accepted_card_ids")
    unlocked_cards = payload_card_ids(payload, "unlocked_card_ids")
    selected_cards = payload_card_ids(payload, "selected_card_ids")
    dispatched_cards = payload_card_ids(payload, "dispatched_card_ids")
    dispatch_refs = payload_card_ids(payload, "dispatch_refs")
    ready_cards = payload_card_ids(payload, "ready_card_ids")
    running_cards = payload_card_ids(payload, "running_card_ids")
    blocked_cards = payload_card_ids(payload, "blocked_card_ids")
    completed_cards = payload_card_ids(payload, "completed_card_ids")
    mutated = progress_payload_mutated(payload)
    status = str(payload.get("status") or "").strip()
    if status in {
        ComplexTaskRunStatus.COMPLETED.value,
        ComplexTaskRunStatus.FAILED.value,
        ComplexTaskRunStatus.CANCELLED.value,
    }:
        stop_candidate = f"terminal:{status}"
    elif not mutated and running_cards:
        stop_candidate = "waiting_on_running_cards"
    elif not mutated and ready_cards:
        stop_candidate = "waiting_on_ready_cards"
    elif not mutated:
        stop_candidate = "stable_noop"
    else:
        stop_candidate = "continue"
    return {
        "pass": int(pass_index),
        "status": status or "-",
        "current_phase": str(payload.get("current_phase") or "").strip() or "-",
        "mutated": mutated,
        "stop_candidate": stop_candidate,
        "synced_count": len(synced_cards),
        "accepted_count": len(accepted_cards),
        "unlocked_count": len(unlocked_cards),
        "selected_count": len(selected_cards),
        "dispatched_count": len(dispatched_cards),
        "dispatch_ref_count": len(dispatch_refs),
        "ready_count": len(ready_cards),
        "running_count": len(running_cards),
        "blocked_count": len(blocked_cards),
        "completed_count": len(completed_cards),
    }


def continue_orchestration_run_impl(
    runtime: Any,
    run_id: str,
    *,
    max_passes: int = 8,
    dispatch_ready: bool = True,
    progress_orchestration_run_fn: Any,
) -> dict[str, Any]:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        raise ValueError("orchestrate_continue requires a run_id")
    bounded_passes = max(1, int(max_passes))
    pass_count = 0
    aggregated_synced: list[str] = []
    aggregated_accepted: list[str] = []
    aggregated_unlocked: list[str] = []
    aggregated_selected: list[str] = []
    aggregated_dispatched: list[str] = []
    aggregated_dispatch_refs: list[str] = []
    pass_summaries: list[dict[str, Any]] = []
    stopped_reason = "max_passes_reached"
    stop_pass = 0
    last_payload: dict[str, Any] | None = None
    for _ in range(bounded_passes):
        pass_count += 1
        payload = progress_orchestration_run_fn(
            runtime, resolved_run_id, dispatch_ready=dispatch_ready
        )
        last_payload = payload
        extend_unique(aggregated_synced, payload.get("synced_card_ids"))
        extend_unique(aggregated_accepted, payload.get("accepted_card_ids"))
        extend_unique(aggregated_unlocked, payload.get("unlocked_card_ids"))
        extend_unique(aggregated_selected, payload.get("selected_card_ids"))
        extend_unique(aggregated_dispatched, payload.get("dispatched_card_ids"))
        extend_unique(aggregated_dispatch_refs, payload.get("dispatch_refs"))
        pass_summaries.append(continue_pass_summary(pass_count, payload))
        status = str(payload.get("status") or "").strip()
        if status in {
            ComplexTaskRunStatus.COMPLETED.value,
            ComplexTaskRunStatus.FAILED.value,
            ComplexTaskRunStatus.CANCELLED.value,
        }:
            stopped_reason = f"terminal:{status}"
            stop_pass = pass_count
            break
        if not progress_payload_mutated(payload):
            stopped_reason = str(pass_summaries[-1].get("stop_candidate") or "stable_noop")
            stop_pass = pass_count
            break
    if not isinstance(last_payload, dict):
        raise ValueError(f"unknown orchestration run: {resolved_run_id}")
    if stop_pass <= 0:
        stop_pass = pass_count
    mutated_pass_count = sum(1 for item in pass_summaries if bool(item.get("mutated")))
    last_mutated_pass = 0
    for item in reversed(pass_summaries):
        if bool(item.get("mutated")):
            last_mutated_pass = int(item.get("pass") or 0)
            break
    return {
        **last_payload,
        "max_passes": bounded_passes,
        "pass_count": pass_count,
        "passes_executed": pass_count,
        "stopped_reason": stopped_reason,
        "stop_pass": stop_pass,
        "mutated_pass_count": mutated_pass_count,
        "last_mutated_pass": last_mutated_pass,
        "pass_summaries": pass_summaries,
        "synced_card_ids": aggregated_synced,
        "accepted_card_ids": aggregated_accepted,
        "unlocked_card_ids": aggregated_unlocked,
        "selected_card_ids": aggregated_selected,
        "dispatched_card_ids": aggregated_dispatched,
        "dispatch_refs": aggregated_dispatch_refs,
    }
