from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "approval_continuation_claude_code_ab.py"
SPEC = importlib.util.spec_from_file_location("approval_continuation_claude_code_ab", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_claude_prompt_uses_native_bash_and_write_tools() -> None:
    cases = {case.name: case for case in MODULE.CASES}

    shell_prompt = MODULE._claude_prompt_for_case(cases["approve_exec_command"])
    write_prompt = MODULE._claude_prompt_for_case(cases["approve_apply_patch"])

    assert "`Bash` tool" in shell_prompt
    assert "approval-approved" in shell_prompt
    assert "approval_live_approve.txt" in shell_prompt
    assert "`Write` tool" in write_prompt
    assert '"file_path": "approval_patch_approve.txt"' in write_prompt
    assert "approval-patch-approved" in write_prompt


def test_permission_response_maps_approve_and_reject() -> None:
    cases = {case.name: case for case in MODULE.CASES}

    approve = MODULE._permission_response_for_case(
        case=cases["approve_exec_command"],
        request_id="request-1",
        tool_use_id="tool-1",
    )
    reject = MODULE._permission_response_for_case(
        case=cases["reject_apply_patch"],
        request_id="request-2",
        tool_use_id="tool-2",
    )

    assert approve["response"]["request_id"] == "request-1"
    assert approve["response"]["response"]["behavior"] == "allow"
    assert approve["response"]["response"]["updatedInput"] == {}
    assert approve["response"]["response"]["toolUseID"] == "tool-1"
    assert reject["response"]["request_id"] == "request-2"
    assert reject["response"]["response"]["behavior"] == "deny"
    assert reject["response"]["response"]["decisionClassification"] == "user_reject"


def test_summarize_claude_lines_detects_permission_and_completion() -> None:
    lines = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Bash",
                        "input": {"command": "printf hi > hi.txt"},
                    }
                ]
            },
        },
        {
            "type": "control_request",
            "request_id": "request-1",
            "request": {
                "subtype": "can_use_tool",
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "description": "write hi",
                "input": {"command": "printf hi > hi.txt"},
            },
        },
        {"type": "result", "subtype": "success", "terminal_reason": "completed", "result": "done"},
    ]
    decisions = [
        {
            "request_id": "request-1",
            "tool_name": "Bash",
            "tool_use_id": "tool-1",
            "decision": "approve",
        }
    ]

    summary = MODULE._summarize_claude_lines(lines, decisions)

    assert summary["control_request_count"] == 1
    assert summary["control_requests"][0]["tool_name"] == "Bash"
    assert summary["assistant_tool_uses"][0]["name"] == "Bash"
    assert summary["completed_turn"] is True
    assert summary["terminal_reason"] == "completed"


def test_case_verdict_passes_for_approve_side_effects() -> None:
    case = {case.name: case for case in MODULE.CASES}["approve_exec_command"]
    claude_code = {
        "run": {"exit_code": 0, "timed_out": False},
        "summary": {
            "control_requests": [{"tool_name": "Bash"}],
            "decisions": [{"tool_name": "Bash", "decision": "approve"}],
            "completed_turn": True,
        },
        "file": {"exists": True, "content": case.expected_content},
    }

    verdict, reasons = MODULE._case_verdict(
        case=case,
        agenthub_case={"verdict": "pass"},
        agenthub_file={"exists": True, "content": case.expected_content},
        claude_code=claude_code,
    )

    assert verdict == "pass"
    assert reasons == []


def test_reject_case_verdict_requires_absent_files() -> None:
    case = {case.name: case for case in MODULE.CASES}["reject_apply_patch"]
    claude_code = {
        "run": {"exit_code": 0, "timed_out": False},
        "summary": {
            "control_requests": [{"tool_name": "Write"}],
            "decisions": [{"tool_name": "Write", "decision": "reject"}],
            "completed_turn": True,
        },
        "file": {"exists": False, "content": ""},
    }

    verdict, reasons = MODULE._case_verdict(
        case=case,
        agenthub_case={"verdict": "pass"},
        agenthub_file={"exists": False, "content": ""},
        claude_code=claude_code,
    )

    assert verdict == "pass"
    assert reasons == []


def test_main_dry_run_writes_report(tmp_path: Path) -> None:
    exit_code = MODULE.main(
        [
            "--out-root",
            str(tmp_path / "out"),
            "--case",
            "approve_exec_command",
            "--agenthub-provider",
            "anthropic",
            "--agenthub-model",
            "claude_sonnet_46",
            "--claude-model",
            "sonnet",
        ]
    )

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["dry_run"] is True
    assert report["verdict"] == "dry_run"
    assert report["case_count"] == 1
    assert report["results"][0]["case"] == "approve_exec_command"
    assert (tmp_path / "out" / "summary.md").exists()
