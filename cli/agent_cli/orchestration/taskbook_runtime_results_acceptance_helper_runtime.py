from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_models import CardResult, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_state import CardAcceptanceDecision, CardResultStatus, TaskCardKind


def completed_result_decision(
    result: CardResult,
    *,
    card: TaskCard | None,
    state: TaskCardState | None,
    reviewer_policy: dict[str, Any] | None,
    policy_mapping_fn: Any,
    risk_requires_review_fn: Any,
    risk_reject_reason_fn: Any,
    risk_block_reason_fn: Any,
    workspace_change_requires_review_fn: Any,
    workspace_change_requires_tests_fn: Any,
    rework_or_escalate_block_fn: Any,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    effective_policy = policy_mapping_fn(reviewer_policy)
    card_kind = card.kind if isinstance(card, TaskCard) else None
    is_read_only_card = card_kind is TaskCardKind.READ_ONLY
    has_workspace_changes = bool(list(result.modified_files or []))
    review_risks = list(result.risks or [])
    has_review_risks = bool(review_risks)
    has_test_evidence = bool(list(result.test_commands or []))

    if result.blockers:
        return (CardAcceptanceDecision.BLOCK, "completed_result_has_blockers", [])
    if result.rework_required:
        return rework_or_escalate_block_fn(
            "completed_result_marked_rework",
            result=result,
            state=state,
            reviewer_policy=effective_policy,
            card_kind=card_kind,
        )
    if result.needs_review:
        return (CardAcceptanceDecision.BLOCK, result.suggested_next_action or "manual_review_required", [])
    if has_review_risks and risk_requires_review_fn(effective_policy, card_kind=card_kind):
        reject_reason = risk_reject_reason_fn(
            review_risks,
            policy=effective_policy,
            card_kind=card_kind,
        )
        if reject_reason:
            return (CardAcceptanceDecision.REJECT, reject_reason, [])
        return (CardAcceptanceDecision.BLOCK, risk_block_reason_fn(review_risks, policy=effective_policy), [])
    if not is_read_only_card and has_workspace_changes and workspace_change_requires_review_fn(effective_policy):
        return (CardAcceptanceDecision.BLOCK, "reviewer_policy_workspace_change_requires_review", [])
    if has_workspace_changes and workspace_change_requires_tests_fn(effective_policy, card_kind=card_kind) and not has_test_evidence:
        return (CardAcceptanceDecision.BLOCK, "workspace_change_missing_test_evidence", [])
    if not is_read_only_card and has_workspace_changes:
        return (
            CardAcceptanceDecision.ACCEPT,
            "auto_accept_workspace_change_with_test_evidence",
            [f"{result.card_id}:accepted"],
        )
    if is_read_only_card and has_workspace_changes:
        return (CardAcceptanceDecision.BLOCK, "read_only_card_reported_workspace_change", [])
    if result.status is CardResultStatus.COMPLETED and not result.blockers and not result.rework_required and not result.needs_review:
        return (
            CardAcceptanceDecision.ACCEPT,
            "auto_accept_read_only_clean_result",
            [f"{result.card_id}:accepted"],
        )
    return (CardAcceptanceDecision.BLOCK, result.suggested_next_action or "manual_review_required", [])


def effective_attempt(result: CardResult, state: TaskCardState | None) -> int:
    result_attempt = int(getattr(result, "attempt", 0) or 0)
    state_attempt = int(getattr(state, "attempt", 0) or 0) if isinstance(state, TaskCardState) else 0
    return max(result_attempt, state_attempt)


def rework_or_escalate_block(
    base_reason: str,
    *,
    result: CardResult,
    state: TaskCardState | None,
    reviewer_policy: dict[str, Any] | None,
    card_kind: TaskCardKind | None,
    policy_mapping_fn: Any,
    rework_escalation_threshold_fn: Any,
    effective_attempt_fn: Any,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    policy = policy_mapping_fn(reviewer_policy)
    threshold = rework_escalation_threshold_fn(
        policy,
        card_kind=card_kind,
    )
    if effective_attempt_fn(result, state) >= threshold:
        return (CardAcceptanceDecision.BLOCK, f"{base_reason}_escalated_after_retries", [])
    return (CardAcceptanceDecision.REWORK, base_reason, [])


def auto_acceptance_decision(
    result: CardResult,
    *,
    card: TaskCard | None,
    state: TaskCardState | None,
    reviewer_policy: dict[str, Any] | None,
    completed_result_decision_fn: Any,
    rework_or_escalate_block_fn: Any,
    kind_rule_bool_fn: Any,
    kind_rule_str_list_fn: Any,
    policy_mapping_fn: Any,
    policy_str_list_fn: Any,
    contains_policy_keyword_fn: Any,
) -> tuple[CardAcceptanceDecision, str, list[str]]:
    card_kind = card.kind if isinstance(card, TaskCard) else None
    if result.status is CardResultStatus.COMPLETED:
        return completed_result_decision_fn(
            result,
            card=card,
            state=state,
            reviewer_policy=reviewer_policy,
        )
    if result.status is CardResultStatus.TIMED_OUT:
        if result.rework_required:
            decision, reason, accepted_facts = rework_or_escalate_block_fn(
                result.suggested_next_action or "execution_timed_out_retry_recommended",
                result=result,
                state=state,
                reviewer_policy=reviewer_policy,
                card_kind=card_kind,
            )
            return (decision, reason, accepted_facts)
        retry_by_kind = kind_rule_bool_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_failed_requires_rework_by_kind",
            card_kind=card_kind,
        )
        retry_keywords = policy_str_list_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_failure_reason_keywords",
            "retry_timeout_reason_keywords",
        )
        retry_keywords_by_kind = kind_rule_str_list_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_timeout_reason_keywords_by_kind",
            card_kind=card_kind,
        )
        if retry_keywords_by_kind:
            retry_keywords = retry_keywords_by_kind
        retry_reason = contains_policy_keyword_fn(result.suggested_next_action or "", retry_keywords)
        if retry_by_kind or retry_reason:
            decision, reason, accepted_facts = rework_or_escalate_block_fn(
                result.suggested_next_action or "execution_timed_out_retry_recommended",
                result=result,
                state=state,
                reviewer_policy=reviewer_policy,
                card_kind=card_kind,
            )
            return (decision, reason, accepted_facts)
        return (CardAcceptanceDecision.REJECT, result.suggested_next_action or "execution_timed_out", [])
    if result.status is CardResultStatus.FAILED:
        if result.rework_required:
            decision, reason, accepted_facts = rework_or_escalate_block_fn(
                result.suggested_next_action or "execution_failed_retry_recommended",
                result=result,
                state=state,
                reviewer_policy=reviewer_policy,
                card_kind=card_kind,
            )
            return (decision, reason, accepted_facts)
        retry_by_kind = kind_rule_bool_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_failed_requires_rework_by_kind",
            card_kind=card_kind,
        )
        retry_keywords = policy_str_list_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_failure_reason_keywords",
            "retry_failed_reason_keywords",
        )
        retry_keywords_by_kind = kind_rule_str_list_fn(
            policy_mapping_fn(reviewer_policy),
            "retry_failed_reason_keywords_by_kind",
            card_kind=card_kind,
        )
        if retry_keywords_by_kind:
            retry_keywords = retry_keywords_by_kind
        retry_reason = contains_policy_keyword_fn(result.suggested_next_action or "", retry_keywords)
        if retry_by_kind or retry_reason:
            decision, reason, accepted_facts = rework_or_escalate_block_fn(
                result.suggested_next_action or "execution_failed_retry_recommended",
                result=result,
                state=state,
                reviewer_policy=reviewer_policy,
                card_kind=card_kind,
            )
            return (decision, reason, accepted_facts)
        if result.blockers:
            return (CardAcceptanceDecision.REJECT, "execution_failed_with_blockers", [])
        return (CardAcceptanceDecision.REJECT, result.suggested_next_action or "execution_failed", [])
    if result.status is CardResultStatus.CANCELLED:
        return (
            CardAcceptanceDecision.REJECT,
            result.suggested_next_action or "execution_cancelled",
            [],
        )
    return (
        CardAcceptanceDecision.REJECT,
        result.suggested_next_action or result.status.value,
        [],
    )


def is_manual_review_block_reason(reason: str, *, manual_review_block_reasons: set[str]) -> bool:
    normalized = str(reason or "").strip()
    if not normalized:
        return False
    if normalized in manual_review_block_reasons:
        return True
    if normalized.startswith("reviewer_policy_risk_keyword:"):
        return True
    return False


def replan_followup_actions(
    *,
    result: CardResult,
    decision: CardAcceptanceDecision,
    reason: str,
    card: TaskCard | None,
    state: TaskCardState | None,
    reviewer_policy: dict[str, Any] | None,
    effective_attempt_fn: Any,
    is_manual_review_block_reason_fn: Any,
) -> list[dict[str, Any]]:
    del reviewer_policy
    normalized_reason = str(reason or "").strip()
    suggested_next_action = str(result.suggested_next_action or "").strip().lower()
    if "replan" in suggested_next_action:
        return [
            {
                "action": "replan_candidate",
                "scope": "card",
                "trigger": "suggested_next_action",
                "reason": normalized_reason or suggested_next_action,
                "card_id": result.card_id,
                "result_id": result.result_id,
                "attempt": effective_attempt_fn(result, state),
            }
        ]
    if decision is CardAcceptanceDecision.BLOCK:
        if normalized_reason.endswith("_escalated_after_retries"):
            return [
                {
                    "action": "replan_candidate",
                    "scope": "card",
                    "trigger": "rework_escalated_after_retries",
                    "reason": normalized_reason,
                    "card_id": result.card_id,
                    "result_id": result.result_id,
                    "attempt": effective_attempt_fn(result, state),
                }
            ]
        if is_manual_review_block_reason_fn(normalized_reason):
            return []
        if result.status in {CardResultStatus.FAILED, CardResultStatus.TIMED_OUT}:
            return [
                {
                    "action": "replan_candidate",
                    "scope": "run",
                    "trigger": "terminal_failure_blocked",
                    "reason": normalized_reason or result.status.value,
                    "card_id": result.card_id,
                    "result_id": result.result_id,
                    "attempt": effective_attempt_fn(result, state),
                }
            ]
        return []
    if decision is CardAcceptanceDecision.REJECT and result.status in {
        CardResultStatus.FAILED,
        CardResultStatus.TIMED_OUT,
        CardResultStatus.CANCELLED,
    }:
        return [
            {
                "action": "replan_candidate",
                "scope": "run",
                "trigger": "terminal_reject",
                "reason": normalized_reason or result.status.value,
                "card_id": result.card_id,
                "result_id": result.result_id,
                "attempt": effective_attempt_fn(result, state),
            }
        ]
    if decision is CardAcceptanceDecision.REJECT and any(
        str(item or "").strip().startswith("out_of_scope_files")
        for item in list(result.blockers or [])
    ):
        return [
            {
                "action": "replan_candidate",
                "scope": "run",
                "trigger": "out_of_scope_blocker",
                "reason": normalized_reason or "out_of_scope_files",
                "card_id": result.card_id,
                "result_id": result.result_id,
                "attempt": effective_attempt_fn(result, state),
            }
        ]
    if card is not None:
        del card
    return []
