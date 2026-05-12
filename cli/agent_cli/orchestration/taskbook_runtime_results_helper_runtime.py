from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration import taskbook_runtime_results_acceptance_helper_runtime as acceptance_helper_runtime
from cli.agent_cli.orchestration import taskbook_runtime_results_policy_runtime as policy_runtime
from cli.agent_cli.orchestration import taskbook_runtime_results_parts_helper_runtime as parts_helper_runtime
from cli.agent_cli.orchestration.taskbook_models import CardAcceptance, CardResult, ExecutionRef, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_projection_runtime import (
    normalize_join_next_action,
    normalize_join_result_state,
    normalize_join_summary,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    TaskCardKind,
)

_MANUAL_REVIEW_BLOCK_REASONS = {
    "manual_review_required",
    "workspace_change_missing_test_evidence",
    "reviewer_policy_workspace_change_requires_review",
    "staged_workspace_review_required",
    "read_only_card_reported_workspace_change",
}

_policy_mapping = policy_runtime.policy_mapping
_policy_bool = policy_runtime.policy_bool
_policy_int = policy_runtime.policy_int
_policy_str_list = policy_runtime.policy_str_list
_contains_policy_keyword = policy_runtime.contains_policy_keyword
_card_kind_label = policy_runtime.card_kind_label
_coerce_kind_token = policy_runtime.coerce_kind_token
_kind_rule_bool = policy_runtime.kind_rule_bool
_kind_rule_int = policy_runtime.kind_rule_int
_kind_rule_str_list = policy_runtime.kind_rule_str_list
_workspace_change_requires_review = policy_runtime.workspace_change_requires_review
_rework_escalation_min_attempts = policy_runtime.rework_escalation_min_attempts
_rework_escalation_threshold = policy_runtime.rework_escalation_threshold
_risk_requires_review = policy_runtime.risk_requires_review
_risk_block_reason = policy_runtime.risk_block_reason
_risk_reject_reason = policy_runtime.risk_reject_reason
_workspace_change_requires_tests = policy_runtime.workspace_change_requires_tests


def relative_paths(root: Path, value: Any, *, string_list_fn: Any) -> list[str]:
    return parts_helper_runtime.relative_paths(root, value, string_list_fn=string_list_fn)


def delegated_commands(snapshot: dict[str, Any], *, selector_value_fn: Any) -> list[str]:
    return parts_helper_runtime.delegated_commands(snapshot, selector_value_fn=selector_value_fn)


def delegated_result_parts(
    *,
    card: TaskCard,
    execution_ref: ExecutionRef,
    snapshot: dict[str, Any],
    result_contract: dict[str, Any],
    terminal_status: CardResultStatus,
    root: Path,
    string_list_fn: Any,
    selector_value_fn: Any,
) -> dict[str, Any]:
    return parts_helper_runtime.delegated_result_parts(
        card=card,
        execution_ref=execution_ref,
        snapshot=snapshot,
        result_contract=result_contract,
        terminal_status=terminal_status,
        root=root,
        string_list_fn=string_list_fn,
        selector_value_fn=selector_value_fn,
        relative_paths_fn=relative_paths,
        delegated_commands_fn=delegated_commands,
        normalize_join_result_state_fn=normalize_join_result_state,
        normalize_join_next_action_fn=normalize_join_next_action,
        normalize_join_summary_fn=normalize_join_summary,
    )


def background_result_parts(
    payload: dict[str, Any],
    *,
    execution_ref: ExecutionRef,
    artifact: dict[str, Any],
    terminal_status: CardResultStatus,
    string_list_fn: Any,
    selector_value_fn: Any,
) -> dict[str, Any]:
    return parts_helper_runtime.background_result_parts(
        payload,
        execution_ref=execution_ref,
        artifact=artifact,
        terminal_status=terminal_status,
        string_list_fn=string_list_fn,
        selector_value_fn=selector_value_fn,
        normalize_join_result_state_fn=normalize_join_result_state,
        normalize_join_next_action_fn=normalize_join_next_action,
        normalize_join_summary_fn=normalize_join_summary,
    )


def _completed_result_decision(
    result: CardResult,
    *,
    card: TaskCard | None = None,
    state: TaskCardState | None = None,
    reviewer_policy: dict[str, Any] | None = None,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    return acceptance_helper_runtime.completed_result_decision(
        result,
        card=card,
        state=state,
        reviewer_policy=reviewer_policy,
        policy_mapping_fn=_policy_mapping,
        risk_requires_review_fn=_risk_requires_review,
        risk_reject_reason_fn=_risk_reject_reason,
        risk_block_reason_fn=_risk_block_reason,
        workspace_change_requires_review_fn=_workspace_change_requires_review,
        workspace_change_requires_tests_fn=_workspace_change_requires_tests,
        rework_or_escalate_block_fn=_rework_or_escalate_block,
    )


def _effective_attempt(result: CardResult, state: TaskCardState | None) -> int:
    return acceptance_helper_runtime.effective_attempt(result, state)


def _rework_or_escalate_block(
    base_reason: str,
    *,
    result: CardResult,
    state: TaskCardState | None,
    reviewer_policy: dict[str, Any] | None = None,
    card_kind: TaskCardKind | None = None,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    return acceptance_helper_runtime.rework_or_escalate_block(
        base_reason,
        result=result,
        state=state,
        reviewer_policy=reviewer_policy,
        card_kind=card_kind,
        policy_mapping_fn=_policy_mapping,
        rework_escalation_threshold_fn=_rework_escalation_threshold,
        effective_attempt_fn=_effective_attempt,
    )


def auto_acceptance_decision(
    result: CardResult,
    *,
    card: TaskCard | None = None,
    state: TaskCardState | None = None,
    reviewer_policy: dict[str, Any] | None = None,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    return acceptance_helper_runtime.auto_acceptance_decision(
        result,
        card=card,
        state=state,
        reviewer_policy=reviewer_policy,
        completed_result_decision_fn=_completed_result_decision,
        rework_or_escalate_block_fn=_rework_or_escalate_block,
        kind_rule_bool_fn=_kind_rule_bool,
        kind_rule_str_list_fn=_kind_rule_str_list,
        policy_mapping_fn=_policy_mapping,
        policy_str_list_fn=_policy_str_list,
        contains_policy_keyword_fn=_contains_policy_keyword,
    )


def _is_manual_review_block_reason(reason: str) -> bool:
    return acceptance_helper_runtime.is_manual_review_block_reason(
        reason,
        manual_review_block_reasons=_MANUAL_REVIEW_BLOCK_REASONS,
    )


def replan_followup_actions(
    *,
    result: CardResult,
    decision: CardAcceptanceDecision,
    reason: str,
    card: TaskCard | None = None,
    state: TaskCardState | None = None,
    reviewer_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return acceptance_helper_runtime.replan_followup_actions(
        result=result,
        decision=decision,
        reason=reason,
        card=card,
        state=state,
        reviewer_policy=reviewer_policy,
        effective_attempt_fn=_effective_attempt,
        is_manual_review_block_reason_fn=_is_manual_review_block_reason,
    )


def build_acceptance(
    *,
    acceptance_id_value: str,
    run_id: str,
    card_id: str,
    result_id: str,
    decision: CardAcceptanceDecision,
    reason: str,
    accepted_facts_delta: list[str],
    reviewer_provider: str,
    reviewer_model: str,
    followup_actions: list[dict[str, Any]] | None = None,
) -> CardAcceptance:
    return CardAcceptance(
        acceptance_id=acceptance_id_value,
        run_id=run_id,
        card_id=card_id,
        result_id=result_id,
        decision=decision,
        reason=reason,
        accepted_facts_delta=accepted_facts_delta,
        followup_actions=list(followup_actions or []),
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
    )


def item_from_state_ref(latest_ref: str, items: list[Any], *, id_attr: str) -> Any | None:
    ref = str(latest_ref or "").strip()
    if not ref:
        return None
    for item in items:
        if getattr(item, id_attr, "") == ref:
            return item
    return None
