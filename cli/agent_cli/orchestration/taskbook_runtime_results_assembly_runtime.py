from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration import taskbook_runtime_results_helper_runtime
from cli.agent_cli.orchestration.taskbook_models import (
    CardResult,
    ComplexTaskRun,
    ExecutionRef,
    TaskCard,
    TaskCardState,
)
from cli.agent_cli.orchestration.taskbook_state import CardResultStatus


def replan_followup_contract_payload(
    followup: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    candidate = dict(followup)
    pending = dict(candidate)
    pending["pending_state"] = "awaiting_operator_action"
    pending_reason = str(candidate.get("reason") or "").strip()
    if pending_reason:
        pending["pending_reason"] = pending_reason
    scope = str(candidate.get("scope") or "").strip() or "card"
    card_id = str(candidate.get("card_id") or "").strip()
    result_id_text = str(candidate.get("result_id") or "").strip()
    action_id = f"replan:{scope}:{card_id or '-'}:{result_id_text or '-'}"
    operator_action = {
        "action": "replan_taskbook",
        "action_id": action_id,
        "status": "pending",
        "scope": scope,
        "card_id": card_id,
        "result_id": result_id_text,
        "trigger": str(candidate.get("trigger") or "").strip(),
        "reason": pending_reason,
        "command_name": "/orchestrate_confirm",
        "command_args": ["<updated taskbook markdown>"],
        "command": "/orchestrate_confirm <updated taskbook markdown>",
    }
    return candidate, pending, action_id, operator_action


def replan_followup_progress_summary(
    *,
    contract_version: int,
    candidates: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    pending_card_ids: list[str],
    operator_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    scopes: list[str] = []
    triggers: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "").strip()
        if scope and scope not in scopes:
            scopes.append(scope)
        trigger = str(item.get("trigger") or "").strip()
        if trigger and trigger not in triggers:
            triggers.append(trigger)
    pending_reasons: list[str] = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        pending_reason = str(item.get("pending_reason") or "").strip()
        if pending_reason and pending_reason not in pending_reasons:
            pending_reasons.append(pending_reason)
    next_operator_command = ""
    for action in operator_actions:
        if not isinstance(action, dict):
            continue
        command = str(action.get("command") or "").strip()
        if command:
            next_operator_command = command
            break
    return {
        "contract_version": max(0, int(contract_version or 0)),
        "has_replan_followup": bool(candidates or pending or operator_actions),
        "candidate_count": len(candidates),
        "pending_count": len(pending),
        "pending_card_count": len(pending_card_ids),
        "operator_action_count": len(operator_actions),
        "scopes": scopes,
        "triggers": triggers,
        "pending_reasons": pending_reasons,
        "next_operator_command": next_operator_command,
    }


def delegated_card_result(
    *,
    runtime_root_value: Any,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    delegated_index: dict[str, dict[str, Any]],
    delegated_terminal_result_status_fn: Any,
    result_id_fn: Any,
    selector_value_fn: Any,
    string_list_fn: Any,
    test_commands_fn: Any,
    utc_now_iso_fn: Any,
) -> CardResult | None:
    snapshot = delegated_index.get(str(execution_ref.agent_id or "").strip())
    if not isinstance(snapshot, dict):
        return None
    result_contract = dict(snapshot.get("result_contract") or {})
    terminal_status = delegated_terminal_result_status_fn(snapshot, result_contract=result_contract)
    if terminal_status is None:
        return None
    result_parts = taskbook_runtime_results_helper_runtime.delegated_result_parts(
        card=card,
        execution_ref=execution_ref,
        snapshot=snapshot,
        result_contract=result_contract,
        terminal_status=terminal_status,
        root=runtime_root_value,
        string_list_fn=string_list_fn,
        selector_value_fn=selector_value_fn,
    )
    return CardResult(
        result_id=result_id_fn(
            card.card_id, state.attempt, execution_ref, result_parts["fingerprint"]
        ),
        run_id=run.run_id,
        card_id=card.card_id,
        attempt=int(state.attempt or 0),
        status=terminal_status,
        summary=result_parts["summary"],
        modified_files=result_parts["modified_files"],
        commands=result_parts["commands"],
        test_commands=test_commands_fn(result_parts["commands"]),
        artifacts=result_parts["artifacts"],
        risks=result_parts["risks"],
        blockers=result_parts["blockers"],
        needs_review=result_parts["needs_review"],
        rework_required=terminal_status is CardResultStatus.FAILED,
        suggested_next_action=result_parts["suggested_next_action"],
        execution_ref=execution_ref,
        reported_at=selector_value_fn(snapshot.get("updated_at")) or utc_now_iso_fn(),
    )


def background_card_result(
    *,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    background_adapter: Any | None,
    background_terminal_result_status_fn: Any,
    result_id_fn: Any,
    result_reported_at_fn: Any,
    selector_value_fn: Any,
    string_list_fn: Any,
    test_commands_fn: Any,
) -> CardResult | None:
    if background_adapter is None or not hasattr(background_adapter, "get_status"):
        return None
    payload = background_adapter.get_status(str(execution_ref.task_id or "").strip())
    if not isinstance(payload, dict):
        return None
    artifact = dict(payload.get("artifact") or {})
    terminal_status = background_terminal_result_status_fn(payload, artifact=artifact)
    if terminal_status is None:
        return None
    result_parts = taskbook_runtime_results_helper_runtime.background_result_parts(
        payload,
        execution_ref=execution_ref,
        artifact=artifact,
        terminal_status=terminal_status,
        string_list_fn=string_list_fn,
        selector_value_fn=selector_value_fn,
    )
    return CardResult(
        result_id=result_id_fn(
            card.card_id, state.attempt, execution_ref, result_parts["fingerprint"]
        ),
        run_id=run.run_id,
        card_id=card.card_id,
        attempt=int(state.attempt or 0),
        status=result_parts["terminal_status"],
        summary=result_parts["summary"],
        modified_files=result_parts["modified_files"],
        commands=result_parts["commands"],
        test_commands=result_parts["test_commands"] or test_commands_fn(result_parts["commands"]),
        artifacts=result_parts["artifacts"],
        risks=result_parts["risks"],
        blockers=result_parts["blockers"],
        needs_review=result_parts["needs_review"],
        rework_required=result_parts["terminal_status"]
        in {CardResultStatus.FAILED, CardResultStatus.TIMED_OUT},
        suggested_next_action="manual_review_required" if result_parts["needs_review"] else "",
        execution_ref=execution_ref,
        reported_at=result_reported_at_fn(payload),
    )


def visible_child_tab_card_result(
    *,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    snapshot: dict[str, Any],
    terminal_status: CardResultStatus,
    result_id_fn: Any,
    selector_value_fn: Any,
    utc_now_iso_fn: Any,
) -> CardResult | None:
    assignment = dict(snapshot.get("assignment_ref") or {})
    if selector_value_fn(assignment.get("run_id")) != run.run_id:
        return None
    if selector_value_fn(assignment.get("card_id")) != card.card_id:
        return None
    try:
        attempt = int(assignment.get("attempt") or state.attempt or 0)
    except (TypeError, ValueError):
        attempt = int(state.attempt or 0)
    if attempt != int(state.attempt or 0):
        return None
    summary = (
        selector_value_fn(snapshot.get("summary"))
        or selector_value_fn(snapshot.get("error_message"))
        or terminal_status.value
    )
    objective_state = selector_value_fn(snapshot.get("objective_state"))
    error_message = selector_value_fn(snapshot.get("error_message"))
    blockers = [error_message] if error_message else []
    if objective_state in {"claimed_blocked", "claimed_failed"} and summary not in blockers:
        blockers.append(summary)
    suggested_next_action = ""
    if objective_state == "claimed_partial":
        suggested_next_action = "manual_review_required"
    elif objective_state == "claimed_blocked":
        suggested_next_action = "child_reported_blocked"
    elif objective_state == "claimed_failed":
        suggested_next_action = "child_reported_failed"
    elif terminal_status is not CardResultStatus.COMPLETED:
        suggested_next_action = "inspect_child_tab"
    needs_review = bool(
        str(getattr(card.kind, "value", card.kind)) != "read_only"
        or objective_state in {"claimed_partial", "claimed_blocked", "claimed_failed"}
    )
    if needs_review and not suggested_next_action:
        suggested_next_action = "manual_review_required"
    fingerprint = "|".join(
        [
            terminal_status.value,
            selector_value_fn(snapshot.get("run_id")),
            selector_value_fn(snapshot.get("tab_id")),
            selector_value_fn(snapshot.get("terminal_reason")),
            objective_state,
            summary,
            error_message,
        ]
    )
    return CardResult(
        result_id=result_id_fn(card.card_id, state.attempt, execution_ref, fingerprint),
        run_id=run.run_id,
        card_id=card.card_id,
        attempt=int(state.attempt or 0),
        status=terminal_status,
        summary=summary,
        modified_files=[],
        commands=[],
        test_commands=[],
        artifacts=[
            {
                "kind": "visible_child_tab",
                "tab_id": selector_value_fn(snapshot.get("tab_id")),
                "task_run_id": selector_value_fn(snapshot.get("run_id")),
                "terminal_state": selector_value_fn(snapshot.get("terminal_state")),
                "terminal_reason": selector_value_fn(snapshot.get("terminal_reason")),
                "objective_state": objective_state,
            }
        ],
        risks=[],
        blockers=blockers,
        needs_review=needs_review,
        rework_required=terminal_status is CardResultStatus.FAILED,
        suggested_next_action=suggested_next_action,
        execution_ref=execution_ref,
        reported_at=selector_value_fn(snapshot.get("finished_at")) or utc_now_iso_fn(),
    )
