from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_acceptance import (
    apply_acceptance_decision,
    ingest_card_result,
)
from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    TaskCard,
    TaskCardState,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    TaskCardKind,
    TaskCardStatus,
)


def test_ingest_card_result_moves_state_to_review() -> None:
    state = TaskCardState(card_id="CARD-001", status=TaskCardStatus.RUNNING, attempt=1)
    result = CardResult(
        result_id="result_001",
        run_id="ctrun_accept_1",
        card_id="CARD-001",
        attempt=1,
        status=CardResultStatus.COMPLETED,
        reported_at="2026-04-05T10:00:00Z",
    )

    updated = ingest_card_result(state, result)

    assert updated.status is TaskCardStatus.REVIEW
    assert updated.latest_result_ref == "result_001"
    assert updated.finished_at == "2026-04-05T10:00:00Z"


def test_acceptance_accept_updates_run_and_unlocks_dependents() -> None:
    run = ComplexTaskRun(run_id="ctrun_accept_2")
    cards = {
        "CARD-001": TaskCard(card_id="CARD-001", taskbook_version=1, title="schema", kind=TaskCardKind.READ_ONLY),
        "CARD-002": TaskCard(card_id="CARD-002", taskbook_version=1, title="storage", depends_on=["CARD-001"]),
    }
    states = {
        "CARD-001": TaskCardState(card_id="CARD-001", status=TaskCardStatus.REVIEW, attempt=1),
        "CARD-002": TaskCardState(card_id="CARD-002", status=TaskCardStatus.DRAFT, attempt=0),
    }
    acceptance = CardAcceptance(
        acceptance_id="accept_001",
        run_id=run.run_id,
        card_id="CARD-001",
        result_id="result_001",
        decision=CardAcceptanceDecision.ACCEPT,
        accepted_facts_delta=["schema_ready"],
        reviewed_at="2026-04-05T10:01:00Z",
    )

    outcome = apply_acceptance_decision(run, cards=cards, card_states=states, acceptance=acceptance)

    assert outcome.card_states["CARD-001"].status is TaskCardStatus.ACCEPTED
    assert outcome.card_states["CARD-002"].status is TaskCardStatus.READY
    assert outcome.unlocked_card_ids == ["CARD-002"]
    assert outcome.run.accepted_facts == ["schema_ready"]
    assert outcome.run.completed_card_ids == ["CARD-001"]


def test_acceptance_rework_increments_attempt_and_returns_card_to_ready() -> None:
    run = ComplexTaskRun(run_id="ctrun_accept_3")
    cards = {"CARD-003": TaskCard(card_id="CARD-003", taskbook_version=1, title="dispatch")}
    states = {"CARD-003": TaskCardState(card_id="CARD-003", status=TaskCardStatus.REVIEW, attempt=1)}
    acceptance = CardAcceptance(
        acceptance_id="accept_002",
        run_id=run.run_id,
        card_id="CARD-003",
        result_id="result_002",
        decision=CardAcceptanceDecision.REWORK,
        reason="needs better tests",
    )

    outcome = apply_acceptance_decision(run, cards=cards, card_states=states, acceptance=acceptance)

    assert outcome.card_states["CARD-003"].status is TaskCardStatus.READY
    assert outcome.card_states["CARD-003"].attempt == 2
    assert outcome.card_states["CARD-003"].last_error == "rework_required:needs better tests"
    assert outcome.card_states["CARD-003"].last_scheduler_decision == "rework_requested_by_acceptance"


def test_acceptance_block_and_reject_do_not_pollute_accepted_facts() -> None:
    run = ComplexTaskRun(run_id="ctrun_accept_4")
    cards = {"CARD-004": TaskCard(card_id="CARD-004", taskbook_version=1, title="review")}
    states = {"CARD-004": TaskCardState(card_id="CARD-004", status=TaskCardStatus.REVIEW, attempt=1)}

    block = CardAcceptance(
        acceptance_id="accept_block",
        run_id=run.run_id,
        card_id="CARD-004",
        result_id="result_004",
        decision=CardAcceptanceDecision.BLOCK,
        reason="need approval",
    )
    reject = CardAcceptance(
        acceptance_id="accept_reject",
        run_id=run.run_id,
        card_id="CARD-004",
        result_id="result_005",
        decision=CardAcceptanceDecision.REJECT,
        reason="wrong scope",
    )

    blocked = apply_acceptance_decision(run, cards=cards, card_states=states, acceptance=block)
    rejected = apply_acceptance_decision(run, cards=cards, card_states=states, acceptance=reject)

    assert blocked.card_states["CARD-004"].status is TaskCardStatus.BLOCKED
    assert blocked.card_states["CARD-004"].last_error == "blocked:need approval"
    assert blocked.card_states["CARD-004"].last_scheduler_decision == "blocked_by_acceptance_review"
    assert blocked.run.accepted_facts == []
    assert rejected.card_states["CARD-004"].status is TaskCardStatus.READY
    assert rejected.card_states["CARD-004"].attempt == 2
    assert rejected.card_states["CARD-004"].last_error == "rejected:wrong scope"
    assert rejected.card_states["CARD-004"].last_scheduler_decision == "rejected_requires_new_attempt"
    assert rejected.run.accepted_facts == []


def test_acceptance_default_reason_is_filled_for_block_rework_reject() -> None:
    run = ComplexTaskRun(run_id="ctrun_accept_5")
    cards = {"CARD-005": TaskCard(card_id="CARD-005", taskbook_version=1, title="review defaults")}
    states = {"CARD-005": TaskCardState(card_id="CARD-005", status=TaskCardStatus.REVIEW, attempt=3)}

    blocked = apply_acceptance_decision(
        run,
        cards=cards,
        card_states=states,
        acceptance=CardAcceptance(
            acceptance_id="accept_block_default",
            run_id=run.run_id,
            card_id="CARD-005",
            result_id="result_005_a",
            decision=CardAcceptanceDecision.BLOCK,
            reason="",
        ),
    )
    assert blocked.card_states["CARD-005"].last_error == "blocked:reviewer_blocked_progress"

    reworked = apply_acceptance_decision(
        run,
        cards=cards,
        card_states=states,
        acceptance=CardAcceptance(
            acceptance_id="accept_rework_default",
            run_id=run.run_id,
            card_id="CARD-005",
            result_id="result_005_b",
            decision=CardAcceptanceDecision.REWORK,
            reason="",
        ),
    )
    assert reworked.card_states["CARD-005"].last_error == "rework_required:reviewer_requested_rework"

    rejected = apply_acceptance_decision(
        run,
        cards=cards,
        card_states=states,
        acceptance=CardAcceptance(
            acceptance_id="accept_reject_default",
            run_id=run.run_id,
            card_id="CARD-005",
            result_id="result_005_c",
            decision=CardAcceptanceDecision.REJECT,
            reason="",
        ),
    )
    assert rejected.card_states["CARD-005"].last_error == "rejected:reviewer_rejected_result"


def test_acceptance_rework_escalation_block_uses_dedicated_scheduler_decision() -> None:
    run = ComplexTaskRun(run_id="ctrun_accept_6")
    cards = {"CARD-006": TaskCard(card_id="CARD-006", taskbook_version=1, title="retry escalation")}
    states = {"CARD-006": TaskCardState(card_id="CARD-006", status=TaskCardStatus.REVIEW, attempt=2)}

    blocked = apply_acceptance_decision(
        run,
        cards=cards,
        card_states=states,
        acceptance=CardAcceptance(
            acceptance_id="accept_block_escalated",
            run_id=run.run_id,
            card_id="CARD-006",
            result_id="result_006",
            decision=CardAcceptanceDecision.BLOCK,
            reason="execution_failed_retry_recommended_escalated_after_retries",
        ),
    )

    assert blocked.card_states["CARD-006"].status is TaskCardStatus.BLOCKED
    assert blocked.card_states["CARD-006"].last_error == "blocked:execution_failed_retry_recommended_escalated_after_retries"
    assert blocked.card_states["CARD-006"].last_scheduler_decision == "blocked_by_rework_escalation"
