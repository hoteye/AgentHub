from __future__ import annotations

from cli.agent_cli.runtime_services import expert_review_parse_runtime


def test_parse_expert_review_output_from_structured_mapping_returns_canonical_result() -> None:
    result = expert_review_parse_runtime.parse_expert_review_output(
        {
            "summary": "Reviewer flagged two issues.",
            "structured_payload": {
                "verdict": "revise",
                "confidence": "high",
                "recommended_action": "revise_and_recheck",
                "findings": [
                    {
                        "severity": "high",
                        "category": "correctness",
                        "title": "Claim lacks evidence",
                        "detail": "The answer cites a result that does not exist.",
                        "evidence_refs": ["tool:web_search:item_12"],
                    },
                    {
                        "severity": "medium",
                        "category": "completeness",
                        "title": "Missing failure mode",
                        "detail": "The rollback path is not described.",
                    },
                ],
            },
        },
        reviewer_provider="anthropic",
        reviewer_model="claude-opus-4.1",
        cross_provider=True,
        cross_vendor=True,
        scope="current_task",
        focus=["correctness", "evidence"],
        strictness="high",
        review_elapsed_ms="1240",
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Reviewer flagged two issues."

    payload = result["structured_payload"]
    assert payload["verdict"] == "revise"
    assert payload["confidence"] == "high"
    assert payload["reviewer"]["provider"] == "anthropic"
    assert payload["reviewer"]["model"] == "claude-opus-4.1"
    assert "reviewer_provider" not in payload
    assert "reviewer_model" not in payload
    assert payload["cross_provider"] is True
    assert payload["cross_vendor"] is True
    assert payload["scope"] == "current_task"
    assert payload["focus"] == ["correctness", "evidence"]
    assert payload["strictness"] == "high"
    assert payload["review_elapsed_ms"] == 1240
    assert payload["recommended_action"] == "revise_and_recheck"
    assert payload["finding_count"] == 2
    assert payload["findings"][0]["title"] == "Claim lacks evidence"


def test_parse_expert_review_output_recovers_from_degraded_text() -> None:
    result = expert_review_parse_runtime.parse_expert_review_output(
        """
        Verdict: BLOCK
        Confidence: HIGH
        Summary: Reviewer found a release blocker.
        Findings:
        - [critical][risk] Destructive migration - Drops the users table. Evidence refs: tool:schema_diff:item_1
        - [medium][evidence] Missing rollback proof - No rollback test output was cited. Evidence refs: assistant:turn_7, tool:test:item_2
        Recommended action: block_and_revise
        """,
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
        cross_provider=True,
        cross_vendor=False,
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Reviewer found a release blocker."

    payload = result["structured_payload"]
    assert payload["verdict"] == "block"
    assert payload["confidence"] == "high"
    assert payload["recommended_action"] == "block_and_revise"
    assert payload["finding_count"] == 2
    assert payload["findings"] == [
        {
            "severity": "critical",
            "category": "risk",
            "title": "Destructive migration",
            "detail": "Drops the users table.",
            "evidence_refs": ["tool:schema_diff:item_1"],
            "metadata": {},
        },
        {
            "severity": "medium",
            "category": "evidence",
            "title": "Missing rollback proof",
            "detail": "No rollback test output was cited.",
            "evidence_refs": ["assistant:turn_7", "tool:test:item_2"],
            "metadata": {},
        },
    ]


def test_parse_expert_review_output_accepts_nested_reviewer_identity() -> None:
    result = expert_review_parse_runtime.parse_expert_review_output(
        {
            "verdict": "accept",
            "confidence": "medium",
            "reviewer": {
                "provider": "anthropic",
                "model": "claude-sonnet-4.5",
            },
            "summary": "No blocking issues found.",
        }
    )

    assert result["status"] == "ok"
    payload = result["structured_payload"]
    assert payload["reviewer"]["provider"] == "anthropic"
    assert payload["reviewer"]["model"] == "claude-sonnet-4.5"
    assert "reviewer_provider" not in payload
    assert "reviewer_model" not in payload


def test_parse_expert_review_output_returns_stable_parse_failure_for_missing_verdict() -> None:
    result = expert_review_parse_runtime.parse_expert_review_output(
        {
            "summary": "Looks reasonable overall.",
            "findings": ["One unsupported claim remains."],
        },
        reviewer_provider="anthropic",
        reviewer_model="claude-sonnet-4.5",
        scope="latest_turn",
        focus=["evidence"],
    )

    assert result == {
        "status": "error",
        "summary": "Expert review failed while parsing reviewer output.",
        "structured_payload": {
            "tool_family": "expert_review",
            "contract_version": "v2",
            "advisory": True,
            "error_code": "expert_review_parse_failed",
            "retryable": False,
            "stage": "parse",
            "detail": "reviewer_output_missing_verdict",
            "reviewer": {
                "provider": "anthropic",
                "model": "claude-sonnet-4.5",
                "reasoning_strategy": "",
                "reasoning_effort": "",
                "reasoning_mode": "",
                "capability_policy": "capability_matrix_v1",
                "capability_source": "expert_review_reviewer_capability_matrix_v1",
            },
            "scope": "latest_turn",
            "focus": ["evidence"],
            "strictness": "medium",
            "error_metadata": {
                "stage": "parse",
                "has_reviewer": True,
            },
        },
    }


def test_parse_expert_review_output_normalizes_verdict_confidence_and_findings() -> None:
    result = expert_review_parse_runtime.parse_expert_review_output(
        {
            "verdict": "ship_it",
            "confidence": "definitely",
            "findings": {
                "severity": "SEVERE",
                "category": "BUG",
                "title": "",
                "detail": "Need stronger tests.",
                "evidence_ref": "assistant:turn_9",
                "unexpected": {"path": "src/app.py"},
            },
        }
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Expert review completed with 1 finding."

    payload = result["structured_payload"]
    assert payload["verdict"] == "uncertain"
    assert payload["confidence"] == "medium"
    assert payload["recommended_action"] == "gather_more_evidence"
    assert payload["findings"] == [
        {
            "severity": "medium",
            "category": "other",
            "title": "Finding 1",
            "detail": "Need stronger tests.",
            "evidence_refs": ["assistant:turn_9"],
            "metadata": {
                "unexpected": {"path": "src/app.py"},
            },
        }
    ]
