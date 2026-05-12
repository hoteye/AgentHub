from __future__ import annotations

from typing import Any, Callable

from .taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    TaskCardDependencyStatus,
    TaskCardStatus,
    coerce_bool,
    coerce_dict,
    coerce_dict_list,
    coerce_int,
    coerce_str_list,
    coerce_text,
    parse_enum,
)


def task_card_state_payload(state: Any) -> dict[str, Any]:
    return {
        "schema_version": int(state.schema_version),
        "card_id": state.card_id,
        "status": state.status.value,
        "attempt": int(state.attempt),
        "execution_refs": [item.to_dict() for item in state.execution_refs],
        "latest_result_ref": state.latest_result_ref,
        "latest_acceptance_ref": state.latest_acceptance_ref,
        "dependency_status": state.dependency_status.value,
        "owned_file_lock": bool(state.owned_file_lock),
        "last_scheduler_decision": state.last_scheduler_decision,
        "last_error": state.last_error,
        "queued_at": state.queued_at,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "updated_at": state.updated_at,
    }


def task_card_state_kwargs(
    data: dict[str, Any],
    *,
    execution_ref_from_dict: Callable[[dict[str, Any] | None], Any],
    utc_now_iso_fn: Callable[[], str],
    schema_version: int,
) -> dict[str, Any]:
    raw_execution_refs = data.get("execution_refs")
    execution_ref_items = raw_execution_refs if isinstance(raw_execution_refs, list) else []
    return {
        "card_id": coerce_text(data.get("card_id")),
        "status": parse_enum(
            TaskCardStatus,
            data.get("status") or TaskCardStatus.DRAFT.value,
            field_name="task_card_state.status",
        ),
        "attempt": coerce_int(data.get("attempt"), default=0, minimum=0),
        "execution_refs": [
            execution_ref_from_dict(item)
            for item in execution_ref_items
            if isinstance(item, dict)
        ],
        "latest_result_ref": coerce_text(data.get("latest_result_ref")),
        "latest_acceptance_ref": coerce_text(data.get("latest_acceptance_ref")),
        "dependency_status": parse_enum(
            TaskCardDependencyStatus,
            data.get("dependency_status") or TaskCardDependencyStatus.PENDING.value,
            field_name="task_card_state.dependency_status",
        ),
        "owned_file_lock": coerce_bool(data.get("owned_file_lock"), default=False),
        "last_scheduler_decision": coerce_text(data.get("last_scheduler_decision")),
        "last_error": coerce_text(data.get("last_error")),
        "queued_at": coerce_text(data.get("queued_at")),
        "started_at": coerce_text(data.get("started_at")),
        "finished_at": coerce_text(data.get("finished_at")),
        "updated_at": coerce_text(data.get("updated_at"), default=utc_now_iso_fn()),
        "schema_version": coerce_int(data.get("schema_version"), default=schema_version, minimum=1),
    }


def card_result_payload(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": int(result.schema_version),
        "result_id": result.result_id,
        "run_id": result.run_id,
        "card_id": result.card_id,
        "attempt": int(result.attempt),
        "status": result.status.value,
        "summary": result.summary,
        "modified_files": list(result.modified_files),
        "commands": list(result.commands),
        "test_commands": list(result.test_commands),
        "artifacts": [dict(item) for item in result.artifacts],
        "risks": list(result.risks),
        "blockers": list(result.blockers),
        "needs_review": bool(result.needs_review),
        "rework_required": bool(result.rework_required),
        "suggested_next_action": result.suggested_next_action,
        "reported_at": result.reported_at,
    }
    if result.execution_ref is not None:
        payload["execution_ref"] = result.execution_ref.to_dict()
    return payload


def card_result_kwargs(
    data: dict[str, Any],
    *,
    execution_ref_from_dict: Callable[[dict[str, Any] | None], Any],
    utc_now_iso_fn: Callable[[], str],
    schema_version: int,
) -> dict[str, Any]:
    raw_execution_ref = data.get("execution_ref")
    return {
        "result_id": coerce_text(data.get("result_id")),
        "run_id": coerce_text(data.get("run_id")),
        "card_id": coerce_text(data.get("card_id")),
        "attempt": coerce_int(data.get("attempt"), default=0, minimum=0),
        "status": parse_enum(
            CardResultStatus,
            data.get("status") or CardResultStatus.REPORTED.value,
            field_name="card_result.status",
        ),
        "summary": coerce_text(data.get("summary")),
        "modified_files": coerce_str_list(data.get("modified_files")),
        "commands": coerce_str_list(data.get("commands")),
        "test_commands": coerce_str_list(data.get("test_commands")),
        "artifacts": coerce_dict_list(data.get("artifacts")),
        "risks": coerce_str_list(data.get("risks")),
        "blockers": coerce_str_list(data.get("blockers")),
        "needs_review": coerce_bool(data.get("needs_review"), default=True),
        "rework_required": coerce_bool(data.get("rework_required"), default=False),
        "suggested_next_action": coerce_text(data.get("suggested_next_action")),
        "execution_ref": execution_ref_from_dict(raw_execution_ref) if isinstance(raw_execution_ref, dict) else None,
        "reported_at": coerce_text(data.get("reported_at"), default=utc_now_iso_fn()),
        "schema_version": coerce_int(data.get("schema_version"), default=schema_version, minimum=1),
    }


def card_acceptance_payload(acceptance: Any) -> dict[str, Any]:
    return {
        "schema_version": int(acceptance.schema_version),
        "acceptance_id": acceptance.acceptance_id,
        "run_id": acceptance.run_id,
        "card_id": acceptance.card_id,
        "result_id": acceptance.result_id,
        "decision": acceptance.decision.value,
        "reason": acceptance.reason,
        "accepted_facts_delta": list(acceptance.accepted_facts_delta),
        "followup_actions": [dict(item) for item in acceptance.followup_actions],
        "reviewer_provider": acceptance.reviewer_provider,
        "reviewer_model": acceptance.reviewer_model,
        "reviewed_at": acceptance.reviewed_at,
    }


def card_acceptance_kwargs(
    data: dict[str, Any],
    *,
    utc_now_iso_fn: Callable[[], str],
    schema_version: int,
) -> dict[str, Any]:
    return {
        "acceptance_id": coerce_text(data.get("acceptance_id")),
        "run_id": coerce_text(data.get("run_id")),
        "card_id": coerce_text(data.get("card_id")),
        "result_id": coerce_text(data.get("result_id")),
        "decision": parse_enum(
            CardAcceptanceDecision,
            data.get("decision") or CardAcceptanceDecision.REJECT.value,
            field_name="card_acceptance.decision",
        ),
        "reason": coerce_text(data.get("reason")),
        "accepted_facts_delta": coerce_str_list(data.get("accepted_facts_delta")),
        "followup_actions": coerce_dict_list(data.get("followup_actions")),
        "reviewer_provider": coerce_text(data.get("reviewer_provider")),
        "reviewer_model": coerce_text(data.get("reviewer_model")),
        "reviewed_at": coerce_text(data.get("reviewed_at"), default=utc_now_iso_fn()),
        "schema_version": coerce_int(data.get("schema_version"), default=schema_version, minimum=1),
    }


def orchestration_event_payload(event: Any) -> dict[str, Any]:
    return {
        "schema_version": int(event.schema_version),
        "seq": int(event.seq),
        "run_id": event.run_id,
        "card_id": event.card_id,
        "event_type": event.event_type,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "payload": dict(event.payload),
        "created_at": event.created_at,
    }


def orchestration_event_kwargs(
    data: dict[str, Any],
    *,
    utc_now_iso_fn: Callable[[], str],
    schema_version: int,
) -> dict[str, Any]:
    return {
        "seq": coerce_int(data.get("seq"), default=0, minimum=0),
        "run_id": coerce_text(data.get("run_id")),
        "card_id": coerce_text(data.get("card_id")),
        "event_type": coerce_text(data.get("event_type")),
        "actor_type": coerce_text(data.get("actor_type")),
        "actor_id": coerce_text(data.get("actor_id")),
        "from_status": coerce_text(data.get("from_status")),
        "to_status": coerce_text(data.get("to_status")),
        "payload": coerce_dict(data.get("payload")),
        "created_at": coerce_text(data.get("created_at"), default=utc_now_iso_fn()),
        "schema_version": coerce_int(data.get("schema_version"), default=schema_version, minimum=1),
    }
