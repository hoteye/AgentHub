from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    build_expert_review_failure_result,
    build_expert_review_success_result,
)
from cli.agent_cli.runtime_services.expert_review_turn_events_runtime import (
    build_expert_review_completed_turn_event,
    build_expert_review_failed_turn_event,
    build_expert_review_requested_turn_event,
    build_expert_review_running_turn_event,
)


def test_build_expert_review_requested_turn_event_has_canonical_payload() -> None:
    event = build_expert_review_requested_turn_event(
        item_id="er_item_1",
        call_id="toolu_review_1",
        task="Check the latest answer for correctness.",
        focus=["correctness", "evidence", "correctness"],
        artifact_paths=[Path("/tmp/review.py"), "src/handler.py"],
        max_findings="12",
        strictness="HIGH",
    )

    assert event == {
        "type": "item.started",
        "item": {
            "id": "er_item_1",
            "call_id": "toolu_review_1",
            "type": "expert_review",
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "phase": "requested",
            "event_name": "expert_review_requested",
            "status": "in_progress",
            "summary": "Expert review requested.",
            "request": {
                "task": "Check the latest answer for correctness.",
                "scope": "current_task",
                "focus": ["correctness", "evidence"],
                "artifact_paths": ["/tmp/review.py", "src/handler.py"],
                "max_findings": 10,
                "strictness": "high",
            },
            "reviewer": {
                "provider": "",
                "model": "",
                "reasoning_strategy": "",
                "reasoning_effort": "",
                "reasoning_mode": "",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
                "cross_provider": None,
                "cross_vendor": None,
                "selection_reason": "",
            },
            "outcome": {
                "status": "pending",
                "verdict": "",
                "finding_count": 0,
                "error_code": "",
                "retryable": False,
                "review_elapsed_ms": None,
            },
        },
    }


def test_build_expert_review_running_turn_event_projects_reviewer_metadata() -> None:
    event = build_expert_review_running_turn_event(
        item_id="er_item_2",
        task="Check the patch for regressions.",
        scope="current_task",
        focus=["regression", "correctness"],
        artifact_paths=["src/main.py"],
        max_findings=3,
        strictness="medium",
        reviewer_provider="anthropic",
        reviewer_model="claude-opus-4.1",
        reviewer_reasoning_strategy="anthropic_reasoning_effort",
        reviewer_reasoning_effort="high",
        reviewer_reasoning_mode="anthropic.thinking",
        cross_provider=True,
        cross_vendor=True,
        selection_reason="cross_vendor_available",
    )

    assert event == {
        "type": "item.updated",
        "item": {
            "id": "er_item_2",
            "call_id": None,
            "type": "expert_review",
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "phase": "running",
            "event_name": "expert_review_running",
            "status": "in_progress",
            "summary": "Expert review running.",
            "request": {
                "task": "Check the patch for regressions.",
                "scope": "current_task",
                "focus": ["regression", "correctness"],
                "artifact_paths": ["src/main.py"],
                "max_findings": 3,
                "strictness": "medium",
            },
            "reviewer": {
                "provider": "anthropic",
                "model": "claude-opus-4.1",
                "reasoning_strategy": "anthropic_reasoning_effort",
                "reasoning_effort": "high",
                "reasoning_mode": "anthropic.thinking",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
                "cross_provider": True,
                "cross_vendor": True,
                "selection_reason": "cross_vendor_available",
            },
            "outcome": {
                "status": "running",
                "verdict": "",
                "finding_count": 0,
                "error_code": "",
                "retryable": False,
                "review_elapsed_ms": None,
            },
        },
        "updated": {
            "phase": "running",
            "event_name": "expert_review_running",
            "status": "in_progress",
            "summary": "Expert review running.",
        },
    }


def test_build_expert_review_completed_turn_event_reuses_canonical_success_result() -> None:
    event = build_expert_review_completed_turn_event(
        item_id="er_item_3",
        call_id="toolu_review_3",
        task="Review the answer for evidence gaps.",
        verdict="revise",
        confidence="high",
        findings=[
            {
                "severity": "high",
                "category": "evidence",
                "title": "Missing supporting proof",
                "detail": "The claim cites no observable evidence.",
                "evidence_refs": ["assistant:turn_9"],
            }
        ],
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
        reviewer_reasoning_strategy="openai_reasoning_effort",
        reviewer_reasoning_effort="xhigh",
        reviewer_reasoning_mode="responses.reasoning.effort",
        cross_provider=True,
        cross_vendor=False,
        scope="selected_artifacts",
        focus=["evidence", "correctness"],
        artifact_paths=["docs/report.md"],
        max_findings=2,
        strictness="high",
        review_elapsed_ms=4200,
        selection_reason="same_vendor_fallback",
    )

    expected_result = build_expert_review_success_result(
        verdict="revise",
        confidence="high",
        findings=[
            {
                "severity": "high",
                "category": "evidence",
                "title": "Missing supporting proof",
                "detail": "The claim cites no observable evidence.",
                "evidence_refs": ["assistant:turn_9"],
            }
        ],
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
        reviewer_reasoning_strategy="openai_reasoning_effort",
        reviewer_reasoning_effort="xhigh",
        reviewer_reasoning_mode="responses.reasoning.effort",
        cross_provider=True,
        cross_vendor=False,
        scope="selected_artifacts",
        focus=["evidence", "correctness"],
        strictness="high",
        review_elapsed_ms=4200,
    )

    assert event == {
        "type": "item.completed",
        "item": {
            "id": "er_item_3",
            "call_id": "toolu_review_3",
            "type": "expert_review",
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "phase": "completed",
            "event_name": "expert_review_completed",
            "status": "completed",
            "summary": "Expert review completed with 1 finding.",
            "request": {
                "task": "Review the answer for evidence gaps.",
                "scope": "selected_artifacts",
                "focus": ["evidence", "correctness"],
                "artifact_paths": ["docs/report.md"],
                "max_findings": 2,
                "strictness": "high",
            },
            "reviewer": {
                "provider": "openai",
                "model": "gpt-5.4",
                "reasoning_strategy": "openai_reasoning_effort",
                "reasoning_effort": "xhigh",
                "reasoning_mode": "responses.reasoning.effort",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
                "cross_provider": True,
                "cross_vendor": False,
                "selection_reason": "same_vendor_fallback",
            },
            "outcome": {
                "status": "ok",
                "verdict": "revise",
                "finding_count": 1,
                "error_code": "",
                "retryable": False,
                "review_elapsed_ms": 4200,
            },
        },
        "result": expected_result,
    }


def test_build_expert_review_failed_turn_event_reuses_canonical_failure_result() -> None:
    event = build_expert_review_failed_turn_event(
        item_id="er_item_4",
        task="Review the migration summary.",
        error_code="expert_review_delegate_failed",
        retryable=True,
        detail="delegated reviewer timed out",
        reviewer_provider="anthropic",
        reviewer_model="claude-opus-4.1",
        reviewer_reasoning_strategy="anthropic_reasoning_effort",
        reviewer_reasoning_effort="high",
        reviewer_reasoning_mode="anthropic.thinking",
        scope="current_task",
        focus=["risk"],
        artifact_paths=["src/migrate.py"],
        max_findings=4,
        strictness="low",
        review_elapsed_ms="35",
        selection_reason="cross_vendor_available",
    )

    expected_result = build_expert_review_failure_result(
        error_code="expert_review_delegate_failed",
        retryable=True,
        detail="delegated reviewer timed out",
        reviewer_provider="anthropic",
        reviewer_model="claude-opus-4.1",
        reviewer_reasoning_strategy="anthropic_reasoning_effort",
        reviewer_reasoning_effort="high",
        reviewer_reasoning_mode="anthropic.thinking",
        scope="current_task",
        focus=["risk"],
        strictness="low",
        review_elapsed_ms="35",
    )

    assert event == {
        "type": "item.completed",
        "item": {
            "id": "er_item_4",
            "call_id": None,
            "type": "expert_review",
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "phase": "failed",
            "event_name": "expert_review_failed",
            "status": "failed",
            "summary": "Expert review failed while running the reviewer.",
            "request": {
                "task": "Review the migration summary.",
                "scope": "current_task",
                "focus": ["risk"],
                "artifact_paths": ["src/migrate.py"],
                "max_findings": 4,
                "strictness": "low",
            },
            "reviewer": {
                "provider": "anthropic",
                "model": "claude-opus-4.1",
                "reasoning_strategy": "anthropic_reasoning_effort",
                "reasoning_effort": "high",
                "reasoning_mode": "anthropic.thinking",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
                "cross_provider": None,
                "cross_vendor": None,
                "selection_reason": "cross_vendor_available",
            },
            "outcome": {
                "status": "error",
                "verdict": "",
                "finding_count": 0,
                "error_code": "expert_review_delegate_failed",
                "retryable": True,
                "review_elapsed_ms": 35,
            },
        },
        "result": expected_result,
    }


def test_expert_review_turn_events_are_json_serialization_friendly() -> None:
    payload = [
        build_expert_review_requested_turn_event(
            item_id="er_json_requested",
            task="Check the latest answer.",
            focus={"correctness", "evidence"},
            artifact_paths={Path("/tmp/a.py"), Path("/tmp/b.py")},
        ),
        build_expert_review_running_turn_event(
            item_id="er_json_running",
            task="Check the latest answer.",
            reviewer_provider="anthropic",
            reviewer_model="claude-opus-4.1",
            cross_provider="yes",
            cross_vendor="no",
        ),
        build_expert_review_completed_turn_event(
            item_id="er_json_completed",
            task="Check the latest answer.",
            verdict="accept",
            findings=[],
            reviewer_provider="anthropic",
            reviewer_model="claude-opus-4.1",
            review_elapsed_ms=12,
        ),
        build_expert_review_failed_turn_event(
            item_id="er_json_failed",
            task="Check the latest answer.",
            error_code="expert_review_parse_failed",
            detail=Path("/tmp/review.out"),
        ),
    ]

    decoded = json.loads(json.dumps(payload, sort_keys=True))

    assert decoded[0]["item"]["request"]["artifact_paths"] == ["/tmp/a.py", "/tmp/b.py"]
    assert decoded[1]["item"]["reviewer"]["cross_provider"] is True
    assert decoded[1]["item"]["reviewer"]["cross_vendor"] is False
    assert decoded[2]["result"]["structured_payload"]["review_elapsed_ms"] == 12
    assert decoded[3]["result"]["structured_payload"]["detail"] == "/tmp/review.out"
