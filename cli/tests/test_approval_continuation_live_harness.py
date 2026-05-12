from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from cli.agent_cli.workspace_context_assembly_runtime import find_project_root

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "approval_continuation_live_harness_runtime_helpers.py"
SPEC = importlib.util.spec_from_file_location(
    "approval_continuation_live_harness_runtime_helpers", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_prepare_case_workspace_roots_harness_under_workspace(tmp_path: Path) -> None:
    parent_git = tmp_path / ".git"
    parent_git.mkdir()
    workspace = tmp_path / "case" / "workspace"

    MODULE._prepare_case_workspace(workspace)

    assert (workspace / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert (
        find_project_root(
            workspace,
            [".git"],
            safe_resolve=lambda path: Path(path).resolve(),
        )
        == workspace.resolve()
    )


def test_control_response_request_for_case_uses_claude_permission_shape() -> None:
    case = MODULE.LiveCase(
        name="approve_exec_command",
        tool_name="exec_command",
        decision="approve",
        target_file="approval_live_approve.txt",
        expected_content="approval-approved",
    )

    request = MODULE._control_response_request_for_case(
        case=case,
        approval_id="approval_1",
        first_lines=[
            {
                "type": "control_request",
                "request_id": "approval_1",
                "request": {
                    "subtype": "can_use_tool",
                    "tool_name": "Bash",
                    "tool_use_id": "tool_1",
                    "input": {"command": "printf hi > out.txt"},
                },
            }
        ],
    )

    assert request["type"] == "control_response"
    assert request["response"]["request_id"] == "approval_1"
    assert request["response"]["response"]["behavior"] == "allow"
    assert request["response"]["response"]["updatedInput"] == {}
    assert request["response"]["response"]["toolUseID"] == "tool_1"
