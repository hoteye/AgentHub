from __future__ import annotations

from cli.agent_cli import memory_extraction_runtime


def test_extract_memory_candidates_from_last_turn_builds_preview_candidate() -> None:
    turn = {
        "user_text": "变量 API_BASE 的值是 https://api.example.com/v1",
        "assistant_text": "记住了",
    }
    candidates = memory_extraction_runtime.extract_memory_candidates_from_last_turn(
        turn=turn,
        memory_type="reference",
        paths=["/srv/app/.env.example"],
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["memory_type"] == "reference"
    assert candidate["title"]
    assert candidate["summary"]
    assert candidate["body"]
    assert candidate["paths"] == ["/srv/app/.env.example"]
    assert "from_last_turn" in candidate["reasons"]
    assert candidate["decision"] == "safe"
    assert candidate["decision_reason"] == "eligible_auto_writeback"


def test_extract_memory_candidates_marks_sensitive_payload() -> None:
    turn = {
        "user_text": "token 是 sk-abc1234567890",
        "assistant_text": "已记录",
    }
    candidates = memory_extraction_runtime.extract_memory_candidates_from_last_turn(turn=turn)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["blocked_sensitive"] is True
    assert "blocked_sensitive" in candidate["reasons"]
    assert candidate["decision"] == "block"
    assert candidate["decision_reason"] == "contains_sensitive_content"


def test_extract_memory_candidates_marks_low_signal_as_review() -> None:
    turn = {
        "user_text": "记住",
        "assistant_text": "好",
    }
    candidates = memory_extraction_runtime.extract_memory_candidates_from_last_turn(turn=turn)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["decision"] == "review"
    assert candidate["decision_reason"] == "low_signal_short_content"


def test_dedupe_memory_candidates_uses_type_title_summary_key() -> None:
    inputs = [
        {"memory_type": "project", "title": "A", "summary": "B", "body": "x"},
        {"memory_type": "project", "title": "a", "summary": "b", "body": "y"},
        {"memory_type": "reference", "title": "A", "summary": "B", "body": "z"},
    ]
    deduped = memory_extraction_runtime.dedupe_memory_candidates(inputs)
    assert len(deduped) == 2
