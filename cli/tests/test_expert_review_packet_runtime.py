from __future__ import annotations

import json

from cli.agent_cli.models import ResponseInputItem, ThreadHistoryTurn, ToolEvent
from cli.agent_cli.runtime_services.expert_review_packet_runtime import (
    build_expert_review_packet,
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


def test_build_expert_review_packet_has_minimal_observable_shape() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_2",
        user_text="Please review the current answer for correctness and evidence.",
        assistant_text="The handler now returns the normalized payload and keeps the existing provider effort untouched.",
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
            "approval_policy": "never",
            "sandbox_mode": "danger-full-access",
            "policy_constraints": ["reviewer_read_only", "no_raw_reasoning"],
            "changed_files": ["src/handler.py", "tests/test_handler.py"],
            "diff_summary": "Updated the payload normalization branch and left the main provider reasoning_effort unchanged.",
            "test_evidence": [
                {
                    "label": "pytest cli/tests/test_handler.py -q",
                    "status": "passed",
                    "output": "2 passed in 0.31s",
                }
            ],
        },
    )

    assert packet["packet_version"] == "expert_review.v1"
    assert packet["review_request"] == {
        "task": "Check the latest answer for correctness and missing evidence.",
        "scope": "latest_turn",
        "focus": ["correctness", "evidence"],
        "artifact_paths": ["src/handler.py"],
        "max_findings": 4,
        "strictness": "high",
    }
    assert packet["selection"]["selected_turn_ids"] == ["turn_2"]
    assert packet["observable_context"]["user_goal_summary"] == (
        "Please review the current answer for correctness and evidence."
    )
    assert packet["observable_context"]["candidate_summary"].startswith(
        "The handler now returns the normalized payload"
    )

    messages = packet["observable_context"]["messages"]
    assert messages == [
        {
            "turn_id": "turn_2",
            "role": "user",
            "text": "Please review the current answer for correctness and evidence.",
            "truncated": False,
        },
        {
            "turn_id": "turn_2",
            "role": "assistant",
            "text": "The handler now returns the normalized payload and keeps the existing provider effort untouched.",
            "truncated": False,
        },
    ]

    tool_activity = packet["observable_context"]["tool_activity"]
    assert len(tool_activity) == 1
    assert tool_activity[0]["name"] == "read_file"
    assert tool_activity[0]["artifact_paths"] == ["src/handler.py"]
    assert tool_activity[0]["result_preview"].startswith("def normalize_payload")

    artifacts = packet["observable_context"]["artifacts"]
    assert artifacts["requested_paths"] == ["src/handler.py"]
    assert artifacts["changed_files"] == ["src/handler.py", "tests/test_handler.py"]
    assert artifacts["diff_summary_truncated"] is False
    assert artifacts["test_evidence"] == [
        {
            "label": "pytest cli/tests/test_handler.py -q",
            "status": "passed",
            "text": "2 passed in 0.31s",
            "truncated": False,
        }
    ]

    runtime_constraints = packet["observable_context"]["runtime_constraints"]
    assert runtime_constraints["approval_policy"] == "never"
    assert runtime_constraints["sandbox_mode"] == "danger-full-access"
    assert runtime_constraints["policy_constraints"] == [
        "reviewer_read_only",
        "no_raw_reasoning",
    ]
    assert packet["omissions"]["reasoning_traces_excluded"] is True


def test_build_expert_review_packet_scope_behavior() -> None:
    turn_1 = ThreadHistoryTurn(
        turn_id="turn_1",
        user_text="Inspect the old implementation.",
        assistant_text="The old branch strips the wrong field.",
        turn_events=[_tool_turn_event(path="src/old_impl.py", text="legacy output", call_id="call_read_old")],
    )
    turn_2 = ThreadHistoryTurn(
        turn_id="turn_2",
        user_text="Inspect the new implementation.",
        assistant_text="The new branch updates src/current_impl.py and the test fixture.",
        turn_events=[_tool_turn_event(path="src/current_impl.py", text="new output", call_id="call_read_new")],
    )

    current_task_packet = build_expert_review_packet(
        task="Review the task history.",
        scope="current_task",
        thread_turns=[turn_1, turn_2],
        runtime_state={"changed_files": ["src/old_impl.py", "src/current_impl.py", "tests/test_impl.py"]},
    )
    selected_artifacts_packet = build_expert_review_packet(
        task="Review only the selected artifact.",
        scope="selected_artifacts",
        artifact_paths=["src/current_impl.py"],
        thread_turns=[turn_1, turn_2],
        runtime_state={"changed_files": ["src/old_impl.py", "src/current_impl.py", "tests/test_impl.py"]},
    )

    assert current_task_packet["selection"]["selected_turn_ids"] == ["turn_1", "turn_2"]
    assert [message["turn_id"] for message in current_task_packet["observable_context"]["messages"]] == [
        "turn_1",
        "turn_1",
        "turn_2",
        "turn_2",
    ]

    assert selected_artifacts_packet["selection"]["selected_turn_ids"] == ["turn_2"]
    selected_tool_activity = selected_artifacts_packet["observable_context"]["tool_activity"]
    assert len(selected_tool_activity) == 1
    assert selected_tool_activity[0]["artifact_paths"] == ["src/current_impl.py"]
    assert selected_artifacts_packet["observable_context"]["artifacts"]["changed_files"] == [
        "src/current_impl.py"
    ]


def test_build_expert_review_packet_clips_large_outputs_and_minimizes_lists() -> None:
    long_assistant_text = "A" * 900
    long_tool_text = "B" * 900
    long_diff_summary = "C" * 1500

    turn = ThreadHistoryTurn(
        turn_id="turn_clip",
        user_text="Review the large patch.",
        assistant_text=long_assistant_text,
        turn_events=[_tool_turn_event(path="src/clip.py", text=long_tool_text, call_id="call_clip")],
    )

    packet = build_expert_review_packet(
        task="Review the latest large output.",
        thread_turns=[turn],
        runtime_state={
            "changed_files": [f"src/file_{index}.py" for index in range(20)],
            "diff_summary": long_diff_summary,
            "test_evidence": [
                {"label": f"pytest case_{index}", "status": "passed", "output": "D" * 500}
                for index in range(10)
            ],
        },
    )

    assistant_message = packet["observable_context"]["messages"][1]
    assert assistant_message["truncated"] is True
    assert assistant_message["text"].endswith("...")
    assert len(assistant_message["text"]) < len(long_assistant_text)

    tool_activity = packet["observable_context"]["tool_activity"][0]
    assert tool_activity["result_truncated"] is True
    assert tool_activity["result_preview"].endswith("...")
    assert len(tool_activity["result_preview"]) < len(long_tool_text)

    artifacts = packet["observable_context"]["artifacts"]
    assert len(artifacts["changed_files"]) == 16
    assert artifacts["changed_files_truncated"] is True
    assert artifacts["diff_summary_truncated"] is True
    assert artifacts["diff_summary"].endswith("...")
    assert len(artifacts["test_evidence"]) == 8
    assert artifacts["test_evidence_truncated"] is True
    assert all(item["truncated"] is True for item in artifacts["test_evidence"])


def test_build_expert_review_packet_excludes_reasoning_traces() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_reasoning",
        user_text="Review the latest candidate.",
        commentary_text="internal commentary that should not be forwarded",
        response_items=[
            ResponseInputItem(
                item_type="reasoning",
                content=[{"type": "reasoning", "text": "private reasoning trace"}],
            ),
            ResponseInputItem(
                item_type="message",
                role="assistant",
                content=[{"type": "output_text", "text": "Visible final answer"}],
                extra={"phase": "final_answer"},
            ),
        ],
        turn_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "reasoning_item_1",
                    "type": "reasoning",
                    "text": "hidden reasoning text",
                    "summary": [{"type": "summary_text", "text": "hidden summary"}],
                    "encrypted_content": "enc-secret",
                },
            }
        ],
    )

    packet = build_expert_review_packet(
        task="Review the candidate without raw reasoning.",
        thread_turns=[turn],
        tool_outputs=[
            ToolEvent(
                name="read_file",
                ok=True,
                summary="read completed",
                payload={
                    "path": "src/reasoning.py",
                    "output_text": "visible tool output",
                    "reasoning_content": "never include this",
                },
            )
        ],
    )

    serialized = json.dumps(packet, ensure_ascii=False)

    assert "Visible final answer" in serialized
    assert "visible tool output" in serialized
    assert "private reasoning trace" not in serialized
    assert "hidden reasoning text" not in serialized
    assert "enc-secret" not in serialized
    assert "never include this" not in serialized
    assert "internal commentary that should not be forwarded" not in serialized
    assert packet["omissions"]["excluded_sources"] == [
        "commentary_text",
        "response_items.reasoning",
        "turn_events.reasoning",
        "turn_events.encrypted_content",
        "tool_outputs.reasoning_payload",
    ]
