from __future__ import annotations

import json

from cli.agent_cli.models import ThreadHistoryTurn
from cli.agent_cli.runtime_services.expert_review_packet_runtime import (
    build_expert_review_packet,
)
from cli.agent_cli.runtime_services.expert_review_prompt_runtime import (
    build_expert_review_reviewer_prompt,
)


def _tool_turn_event(*, path: str, text: str, call_id: str = "call_read_1") -> dict:
    return {
        "type": "item.completed",
        "item": {
            "id": call_id,
            "type": "mcp_tool_call",
            "tool": "read_file",
            "call_id": call_id,
            "arguments": {"path": path},
            "result": {
                "content": [{"type": "text", "text": text}],
                "structured_content": {"summary": "read_file completed"},
            },
            "status": "completed",
        },
    }


def test_build_expert_review_reviewer_prompt_returns_reviewer_facing_payload() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_2",
        user_text="Please review the current answer for correctness and evidence.",
        assistant_text=(
            "The handler now returns the normalized payload and keeps the existing "
            "provider effort untouched."
        ),
        turn_events=[
            _tool_turn_event(
                path="src/handler.py",
                text="def normalize_payload(raw: str) -> str:\n    return raw.strip()\n",
            )
        ],
    )
    packet = build_expert_review_packet(
        task="Check the latest answer for correctness and missing evidence.",
        scope="latest_turn",
        focus=["correctness", "evidence"],
        artifact_paths=["src/handler.py"],
        max_findings=4,
        strictness="high",
        thread_turns=[turn],
        runtime_state={
            "user_goal_summary": "Verify the latest answer before sending it to the user.",
            "candidate_summary": "Normalized payload path updated; provider effort unchanged.",
            "policy_constraints": ["reviewer_read_only", "no_raw_reasoning"],
        },
    )

    payload = build_expert_review_reviewer_prompt(
        packet,
        policy={
            "additional_instructions": ["Treat unsupported claims as evidence gaps."],
            "reviewer_capability_policy": "capability_matrix_v1",
            "reviewer_capability_source": "expert_review_reviewer_capability_matrix_v1",
            "reviewer_reasoning_strategy": "anthropic_reasoning_effort",
            "reviewer_reasoning_effort": "high",
            "reviewer_reasoning_mode": "anthropic.thinking",
        },
    )

    assert payload["contract_version"] == "v1"
    assert payload["messages"] == [
        {"role": "system", "content": payload["system_prompt"]},
        {"role": "user", "content": payload["user_prompt"]},
    ]
    assert payload["reviewer_packet"]["review_request"] == {
        "task": "Check the latest answer for correctness and missing evidence.",
        "scope": "latest_turn",
        "focus": ["correctness", "evidence"],
        "artifact_paths": ["src/handler.py"],
        "max_findings": 4,
        "strictness": "high",
    }

    metadata = payload["metadata"]
    assert metadata["tool_family"] == "expert_review"
    assert metadata["prompt_contract_version"] == "v1"
    assert metadata["result_contract_version"] == "v2"
    assert metadata["advisory"] is True
    assert metadata["read_only"] is True
    assert metadata["critical"] is True
    assert metadata["reviewer_capability_policy"] == "capability_matrix_v1"
    assert metadata["reviewer_capability_source"] == "expert_review_reviewer_capability_matrix_v1"
    assert metadata["reviewer_reasoning_strategy"] == "anthropic_reasoning_effort"
    assert metadata["reviewer_reasoning_effort"] == "high"
    assert metadata["reviewer_reasoning_mode"] == "anthropic.thinking"
    assert metadata["scope"] == "latest_turn"
    assert metadata["scope_source"] == "review_request"
    assert metadata["focus"] == ["correctness", "evidence"]
    assert metadata["focus_source"] == "review_request"
    assert metadata["strictness"] == "high"
    assert metadata["strictness_source"] == "review_request"
    assert metadata["max_findings"] == 4
    assert metadata["max_findings_source"] == "review_request"
    assert metadata["artifact_paths"] == ["src/handler.py"]
    assert metadata["additional_instructions"] == ["Treat unsupported claims as evidence gaps."]

    system_prompt = payload["system_prompt"]
    assert "advisory, critical, read-only assessment" in system_prompt
    assert "Do not act as the mainline assistant" in system_prompt
    assert "Do not request hidden chain-of-thought" in system_prompt
    assert "Return JSON only with keys" in system_prompt

    user_prompt = payload["user_prompt"]
    assert "task: Check the latest answer for correctness and missing evidence." in user_prompt
    assert "focus: correctness, evidence" in user_prompt
    assert "strictness: high" in user_prompt
    assert "max_findings: 4" in user_prompt
    assert "artifact_paths: src/handler.py" in user_prompt
    assert "Treat unsupported claims as evidence gaps." in user_prompt
    assert "constraint: Advisory only: the mainline model retains final authority." in user_prompt
    assert "Observable review packet" in user_prompt
    assert '"scope": "latest_turn"' in payload["reviewer_packet_json"]


def test_build_expert_review_reviewer_prompt_sanitizes_reasoning_like_fields() -> None:
    packet = build_expert_review_packet(
        task="Review the latest candidate without hidden scratchpads.",
        thread_turns=[
            ThreadHistoryTurn(
                turn_id="turn_privacy",
                user_text="Review the candidate.",
                assistant_text="Visible final answer",
            )
        ],
    )
    packet["observable_context"]["debug"] = {
        "visible_note": "keep me",
        "commentary_text": "internal commentary",
        "reasoning_content": "private reasoning trace",
        "encrypted_content": "enc-secret",
    }
    packet["debug_items"] = [
        {
            "type": "note",
            "text": "visible note",
            "reasoning_trace": "drop trace",
        },
        {
            "type": "reasoning",
            "text": "private scratchpad",
        },
    ]

    payload = build_expert_review_reviewer_prompt(packet)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert "Visible final answer" in serialized
    assert "keep me" in serialized
    assert "visible note" in serialized
    assert "internal commentary" not in serialized
    assert "private reasoning trace" not in serialized
    assert "enc-secret" not in serialized
    assert "drop trace" not in serialized
    assert "private scratchpad" not in serialized
    assert payload["reviewer_packet"]["observable_context"]["debug"] == {"visible_note": "keep me"}
    assert payload["reviewer_packet"]["debug_items"] == [
        {
            "text": "visible note",
            "type": "note",
        }
    ]
    assert payload["metadata"]["sanitized_fields"] == [
        "debug_items.0.reasoning_trace",
        "debug_items.1",
        "observable_context.debug.commentary_text",
        "observable_context.debug.encrypted_content",
        "observable_context.debug.reasoning_content",
    ]


def test_build_expert_review_reviewer_prompt_uses_policy_defaults_for_focus_and_strictness() -> (
    None
):
    packet = {
        "packet_version": "expert_review.v1",
        "review_request": {
            "task": "Review the deployment answer.",
            "focus": [],
            "strictness": "",
            "max_findings": None,
        },
        "observable_context": {
            "candidate_summary": "The answer recommends deploying before verifying the backup.",
            "runtime_constraints": {
                "policy_constraints": ["reviewer_read_only", "no_raw_reasoning"]
            },
        },
        "omissions": {
            "reasoning_traces_excluded": True,
            "excluded_sources": ["commentary_text"],
        },
    }

    payload = build_expert_review_reviewer_prompt(
        packet,
        policy={
            "default_focus": ["risk", "policy"],
            "default_strictness": "high",
            "default_max_findings": 7,
            "additional_instructions": ["Escalate unsupported production-impact claims."],
        },
    )

    metadata = payload["metadata"]
    assert metadata["scope"] == "current_task"
    assert metadata["scope_source"] == "default"
    assert metadata["focus"] == ["risk", "policy"]
    assert metadata["focus_source"] == "policy_default"
    assert metadata["strictness"] == "high"
    assert metadata["strictness_source"] == "policy_default"
    assert metadata["max_findings"] == 7
    assert metadata["max_findings_source"] == "policy_default"
    assert metadata["policy_constraints"] == [
        "advisory_only",
        "read_only_review",
        "no_raw_reasoning_requests",
        "reviewer_read_only",
        "no_raw_reasoning",
    ]

    user_prompt = payload["user_prompt"]
    assert "focus: risk, policy" in user_prompt
    assert "strictness: high" in user_prompt
    assert "max_findings: 7" in user_prompt
    assert "Prioritize these focus areas first: risk, policy." in user_prompt
    assert "Escalate unsupported production-impact claims." in user_prompt
    assert "High: apply an adversarial review bar" in user_prompt
    assert "excluded_sources=commentary_text" in user_prompt
    assert "No raw reasoning requests" in user_prompt


def test_build_expert_review_reviewer_prompt_is_deterministic() -> None:
    packet = {
        "packet_version": "expert_review.v1",
        "review_request": {
            "task": "Review deterministically.",
            "focus": {"evidence", "correctness"},
            "artifact_paths": {"tests/test_handler.py", "src/handler.py"},
            "max_findings": "3",
            "strictness": "medium",
        },
        "observable_context": {
            "candidate_summary": "Answer summary",
            "runtime_constraints": {
                "policy_constraints": {"no_raw_reasoning", "reviewer_read_only"}
            },
        },
        "omissions": {
            "reasoning_traces_excluded": True,
            "excluded_sources": {"response_items.reasoning", "commentary_text"},
        },
    }
    policy = {
        "additional_instructions": {
            "Ground each finding in packet evidence.",
            "Prefer material issues over polish.",
        }
    }

    payload_a = build_expert_review_reviewer_prompt(packet, policy=policy)
    payload_b = build_expert_review_reviewer_prompt(packet, policy=policy)

    assert payload_a == payload_b
    assert payload_a["metadata"]["focus"] == ["correctness", "evidence"]
    assert payload_a["metadata"]["artifact_paths"] == [
        "src/handler.py",
        "tests/test_handler.py",
    ]
    assert payload_a["metadata"]["additional_instructions"] == [
        "Ground each finding in packet evidence.",
        "Prefer material issues over polish.",
    ]
