from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun
from cli.agent_cli.orchestration.taskbook_projection import build_workflows_view
from cli.agent_cli.orchestration.taskbook_state import (
    ComplexTaskRunStatus,
    TaskCardStatus,
)


def compact_text_list(values: list[str]) -> list[str]:
    compact: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in compact:
            compact.append(text)
    return compact


def replan_followup_summary(
    *,
    replan_contract_version: int,
    replan_candidates: list[dict[str, Any]],
    replan_pending: list[dict[str, Any]],
    replan_pending_card_ids: list[str],
    operator_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    scopes = compact_text_list([str(item.get("scope") or "") for item in replan_candidates if isinstance(item, dict)])
    triggers = compact_text_list([str(item.get("trigger") or "") for item in replan_candidates if isinstance(item, dict)])
    pending_reasons = compact_text_list(
        [str(item.get("pending_reason") or "") for item in replan_pending if isinstance(item, dict)]
    )
    next_operator_command = ""
    for action in operator_actions:
        if not isinstance(action, dict):
            continue
        command = str(action.get("command") or "").strip()
        if command:
            next_operator_command = command
            break
    has_followup = bool(replan_candidates or replan_pending or operator_actions)
    return {
        "contract_version": max(0, int(replan_contract_version or 0)),
        "has_replan_followup": has_followup,
        "candidate_count": len(replan_candidates),
        "pending_count": len(replan_pending),
        "pending_card_count": len(replan_pending_card_ids),
        "operator_action_count": len(operator_actions),
        "scopes": scopes,
        "triggers": triggers,
        "pending_reasons": pending_reasons,
        "next_operator_command": next_operator_command,
    }


def run_payload(
    services: Any,
    run: ComplexTaskRun,
    *,
    routing_mode: str,
    routing_reasons: list[str],
    taskbook_source: str,
    selected_card_ids: list[str] | None = None,
    dispatched_card_ids: list[str] | None = None,
    dispatch_refs: list[str] | None = None,
    synced_card_ids: list[str] | None = None,
    accepted_card_ids: list[str] | None = None,
    unlocked_card_ids: list[str] | None = None,
    replan_candidates: list[dict[str, Any]] | None = None,
    replan_pending: list[dict[str, Any]] | None = None,
    replan_pending_card_ids: list[str] | None = None,
    replan_contract_version: int | None = None,
    replan_operator_action_ids: list[str] | None = None,
    operator_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bundle = services.storage.load_run_bundle(run.run_id)
    run_view = build_workflows_view(bundle)
    replan_candidates_items = [dict(item) for item in list(replan_candidates or []) if isinstance(item, dict)]
    replan_pending_items = [dict(item) for item in list(replan_pending or []) if isinstance(item, dict)]
    replan_pending_card_ids_items = [
        str(item) for item in list(replan_pending_card_ids or []) if str(item or "").strip()
    ]
    replan_operator_action_ids_items = [
        str(item) for item in list(replan_operator_action_ids or []) if str(item or "").strip()
    ]
    operator_actions_items = [dict(item) for item in list(operator_actions or []) if isinstance(item, dict)]
    replan_contract_version_value = int(replan_contract_version or 0)
    return {
        "run_id": run.run_id,
        "mode": run.mode.value,
        "status": run.status.value,
        "current_phase": run.current_phase,
        "routing_mode": routing_mode,
        "routing_reasons": list(routing_reasons),
        "taskbook_source": taskbook_source,
        "taskbook_version": int(run.taskbook_version_current),
        "card_count": len(list(run_view.get("cards") or [])),
        "ready_card_ids": list(run.ready_card_ids),
        "running_card_ids": list(run.running_card_ids),
        "blocked_card_ids": list(run.blocked_card_ids),
        "completed_card_ids": list(run.completed_card_ids),
        "selected_card_ids": list(selected_card_ids or []),
        "dispatched_card_ids": list(dispatched_card_ids or []),
        "dispatch_refs": list(dispatch_refs or []),
        "synced_card_ids": list(synced_card_ids or []),
        "accepted_card_ids": list(accepted_card_ids or []),
        "unlocked_card_ids": list(unlocked_card_ids or []),
        "replan_candidates": replan_candidates_items,
        "replan_pending": replan_pending_items,
        "replan_pending_card_ids": replan_pending_card_ids_items,
        "replan_contract_version": replan_contract_version_value,
        "replan_operator_action_ids": replan_operator_action_ids_items,
        "operator_actions": operator_actions_items,
        "replan_followup_summary": replan_followup_summary(
            replan_contract_version=replan_contract_version_value,
            replan_candidates=replan_candidates_items,
            replan_pending=replan_pending_items,
            replan_pending_card_ids=replan_pending_card_ids_items,
            operator_actions=operator_actions_items,
        ),
        "run_path": str(services.storage.run_file_path(run.run_id)),
        "projection_path": str(services.storage.projection_taskbook_path(run.run_id)),
    }


def extend_unique(target: list[str], values: Any) -> None:
    for item in list(values or []):
        text = str(item or "").strip()
        if text and text not in target:
            target.append(text)


def delegated_snapshot_index(runtime: Any) -> dict[str, dict[str, Any]]:
    snapshot_fn = getattr(runtime, "_delegated_agent_state_snapshot", None)
    if not callable(snapshot_fn):
        return {}
    try:
        items = list(snapshot_fn() or [])
    except Exception:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agent_id") or "").strip()
        if agent_id:
            index[agent_id] = dict(item)
    return index


def refresh_run_status(run: ComplexTaskRun, card_states: dict[str, Any]) -> None:
    ready = list(run.ready_card_ids or [])
    running = list(run.running_card_ids or [])
    blocked = list(run.blocked_card_ids or [])
    completed = list(run.completed_card_ids or [])
    review = [card_id for card_id, state in sorted(card_states.items()) if state.status is TaskCardStatus.REVIEW]
    if card_states and len(completed) == len(card_states):
        run.status = ComplexTaskRunStatus.COMPLETED
        run.current_phase = "taskbook_completed"
        run.final_summary = run.final_summary or "all cards accepted"
        return
    if review:
        run.status = ComplexTaskRunStatus.REVIEW
        run.current_phase = "card_review_pending"
        return
    if running:
        run.status = ComplexTaskRunStatus.RUNNING
        run.current_phase = "cards_running"
        return
    if ready:
        run.status = ComplexTaskRunStatus.READY
        run.current_phase = "taskbook_ready"
        return
    if blocked:
        run.status = ComplexTaskRunStatus.BLOCKED
        run.current_phase = "taskbook_blocked"
        return
    run.status = ComplexTaskRunStatus.DRAFT
    run.current_phase = "taskbook_draft"


def planner_identity(runtime: Any, *, selector_value_fn) -> tuple[str, str, str]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    payload = status_getter() if callable(status_getter) else {}
    if not isinstance(payload, dict):
        payload = {}
    provider = selector_value_fn(payload.get("provider_name") or payload.get("provider"))
    model = selector_value_fn(payload.get("provider_model") or payload.get("model"))
    reasoning_effort = selector_value_fn(payload.get("provider_reasoning_effort") or payload.get("reasoning_effort"))
    return (provider, model, reasoning_effort)
