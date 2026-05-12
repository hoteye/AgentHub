from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.runtime_services import expert_review_result_runtime


def test_build_expert_review_success_result_returns_canonical_contract() -> None:
    result = expert_review_result_runtime.build_expert_review_success_result(
        verdict="revise",
        confidence="medium",
        reviewer_provider="anthropic",
        reviewer_model="claude-opus-4.1",
        reviewer_reasoning_strategy="anthropic_reasoning_effort",
        reviewer_reasoning_effort="high",
        reviewer_reasoning_mode="anthropic.thinking",
        cross_provider=True,
        cross_vendor=True,
        scope="latest_turn",
        focus=["correctness", "evidence"],
        findings=[
            {
                "severity": "high",
                "category": "correctness",
                "title": "Claim lacks supporting evidence",
                "detail": "The answer states X but no cited tool result supports it.",
                "evidence_refs": ["tool:web_search:item_12", "assistant:turn_7"],
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Expert review completed with 1 finding."

    payload = result["structured_payload"]
    assert payload["tool_family"] == "expert_review"
    assert payload["contract_version"] == "v2"
    assert payload["advisory"] is True
    assert payload["verdict"] == "revise"
    assert payload["confidence"] == "medium"
    assert payload["cross_provider"] is True
    assert payload["cross_vendor"] is True
    assert payload["reviewer"] == {
        "provider": "anthropic",
        "model": "claude-opus-4.1",
        "reasoning_strategy": "anthropic_reasoning_effort",
        "reasoning_effort": "high",
        "reasoning_mode": "anthropic.thinking",
        "capability_policy": "capability_matrix_v1",
        "capability_source": "expert_review_reviewer_capability_matrix_v1",
    }
    assert "reviewer_provider" not in payload
    assert "reviewer_model" not in payload
    assert "reviewer_reasoning_strategy" not in payload
    assert "reviewer_reasoning_effort" not in payload
    assert "reviewer_reasoning_mode" not in payload
    assert "reviewer_capability_policy" not in payload
    assert "reviewer_capability_source" not in payload
    assert payload["scope"] == "latest_turn"
    assert payload["focus"] == ["correctness", "evidence"]
    assert payload["recommended_action"] == "revise_and_recheck"
    assert payload["finding_count"] == 1
    assert payload["verdict_metadata"] == {
        "advisory": True,
        "confidence": "medium",
        "finding_count": 1,
        "has_findings": True,
        "blocking_verdict": False,
        "recommended_action": "revise_and_recheck",
    }
    assert payload["findings_metadata"] == {
        "count": 1,
        "severity_counts": {
            "low": 0,
            "medium": 0,
            "high": 1,
            "critical": 0,
        },
        "category_counts": {
            "correctness": 1,
            "risk": 0,
            "regression": 0,
            "evidence": 0,
            "completeness": 0,
            "policy": 0,
            "code_quality": 0,
            "other": 0,
        },
        "max_severity": "high",
    }
    assert payload["findings"] == [
        {
            "severity": "high",
            "category": "correctness",
            "title": "Claim lacks supporting evidence",
            "detail": "The answer states X but no cited tool result supports it.",
            "evidence_refs": ["tool:web_search:item_12", "assistant:turn_7"],
            "metadata": {},
        }
    ]


def test_build_expert_review_failure_result_returns_stable_error_contract() -> None:
    result = expert_review_result_runtime.build_expert_review_failure_result(
        error_code="expert_review_no_eligible_provider",
        retryable=False,
        scope="current_task",
        focus=["correctness"],
    )

    assert result == {
        "status": "error",
        "summary": "Expert review is unavailable: fewer than two eligible providers.",
        "structured_payload": {
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "error_code": "expert_review_no_eligible_provider",
            "retryable": False,
            "stage": "gate",
            "detail": "",
            "reviewer": {
                "provider": "",
                "model": "",
                "reasoning_strategy": "",
                "reasoning_effort": "",
                "reasoning_mode": "",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
            },
            "scope": "current_task",
            "focus": ["correctness"],
            "strictness": "medium",
            "error_metadata": {
                "stage": "gate",
                "has_reviewer": False,
            },
        },
    }


def test_expert_review_results_are_advisory_by_construction() -> None:
    success_payload = expert_review_result_runtime.build_expert_review_success_payload(
        verdict="accept",
        findings=[],
    )
    error_payload = expert_review_result_runtime.build_expert_review_error_payload(
        error_code="expert_review_delegate_failed",
        retryable=True,
    )

    assert success_payload["advisory"] is True
    assert success_payload["verdict_metadata"]["advisory"] is True
    assert error_payload["advisory"] is True
    assert error_payload["retryable"] is True


def test_expert_review_result_is_json_serialization_friendly() -> None:
    result = expert_review_result_runtime.build_expert_review_success_result(
        verdict="uncertain",
        confidence="high",
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
        cross_provider=True,
        cross_vendor=False,
        focus=("evidence", "correctness"),
        findings=[
            {
                "severity": "high",
                "category": "evidence",
                "title": "More evidence required",
                "detail": Path("/tmp/review.txt"),
                "evidence_refs": {Path("/tmp/review.txt"), "assistant:turn_8"},
                "metadata": {
                    "artifact_path": Path("/tmp/review.json"),
                    "labels": {"stale", "missing"},
                },
                "exception": RuntimeError("missing data"),
            }
        ],
    )

    encoded = json.dumps(result, sort_keys=True)
    decoded = json.loads(encoded)
    finding = decoded["structured_payload"]["findings"][0]

    assert finding["detail"] == "/tmp/review.txt"
    assert finding["evidence_refs"] == ["/tmp/review.txt", "assistant:turn_8"]
    assert finding["metadata"] == {
        "artifact_path": "/tmp/review.json",
        "exception": "missing data",
        "labels": ["missing", "stale"],
    }
