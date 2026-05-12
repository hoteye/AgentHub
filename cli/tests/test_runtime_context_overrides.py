from __future__ import annotations

import json
import shlex
from pathlib import Path

from cli.agent_cli.gateway_core.state_store import InMemoryGatewayStateStore
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core import run_command_text_result
from cli.agent_cli.runtime_policy import RuntimePolicy


def _make_git_marker(path: Path) -> None:
    path.mkdir()
    (path / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")


def test_runtime_context_snapshot_overrides_drive_turn_prelude(tmp_path) -> None:
    runtime = AgentCliRuntime()
    runtime.set_cwd(tmp_path)
    runtime.set_context_snapshot_overrides(
        environment_snapshot={
            "cwd": str(tmp_path),
            "shell": "bash",
            "current_date": "2026-03-31",
            "timezone": "Asia/Shanghai",
        },
        workspace_snapshot={
            "cwd": str(tmp_path),
            "trust_level": "unknown",
            "instructions_text": "# AENGTHUB.md instructions for test workspace\n\nDo the thing.",
            "instructions_digest": "digest-1",
            "docs": [str(Path(tmp_path))],
            "skills": ["skill-a"],
        },
    )

    environment_messages, environment_snapshot = runtime._environment_context_turn_update()
    workspace_messages, workspace_items, workspace_snapshot = (
        runtime._workspace_context_turn_update()
    )

    assert environment_snapshot["current_date"] == "2026-03-31"
    assert environment_snapshot["timezone"] == "Asia/Shanghai"
    assert environment_messages and "<environment_context>" in environment_messages[0]["content"]
    assert "<current_date>2026-03-31</current_date>" in environment_messages[0]["content"]

    assert workspace_snapshot["instructions_digest"] == "digest-1"
    assert workspace_messages and "REFERENCE_CONTEXT_BASELINE:" in workspace_messages[0]["content"]
    assert "instructions_digest=digest-1" in workspace_messages[0]["content"]
    assert len(workspace_items) == 1
    assert workspace_items[0].metadata["instructions_digest"] == "digest-1"


def test_runtime_environment_context_includes_delegation_summary_as_subagents(tmp_path) -> None:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "shell_kind": "bash",
                "shell_program": "/bin/bash",
                "platform_os": "linux",
                "delegate_subagent": "openai | gpt-5.4 | reasoning=high | source=inherit_main",
                "delegate_teammate": "glm | glm-5 | reasoning=medium | timeout=30 | source=delegation",
            }

    runtime = AgentCliRuntime(agent=_Agent())
    runtime.set_cwd(tmp_path)

    environment_messages, environment_snapshot = runtime._environment_context_turn_update()

    assert environment_snapshot["shell"] == "/bin/bash"
    assert environment_snapshot["subagents"] == (
        "subagent: openai | gpt-5.4 | reasoning=high | source=inherit_main\n"
        "teammate: glm | glm-5 | reasoning=medium | timeout=30 | source=delegation"
    )
    assert "<shell>/bin/bash</shell>" in environment_messages[0]["content"]
    assert environment_messages and "<subagents>" in environment_messages[0]["content"]
    assert (
        "subagent: openai | gpt-5.4 | reasoning=high | source=inherit_main"
        in environment_messages[0]["content"]
    )


def test_runtime_set_cwd_updates_workspace_root_but_preserves_harness_root(tmp_path) -> None:
    runtime = AgentCliRuntime()
    original_harness_root = Path(runtime.tools.HARNESS_ROOT)

    runtime.set_cwd(tmp_path)

    assert Path(runtime.tools.WORKSPACE_ROOT) == tmp_path.resolve()
    assert Path(runtime.tools.PROJECT_ROOT) == tmp_path.resolve()
    assert Path(runtime.tools.HARNESS_ROOT) == original_harness_root


def test_runtime_set_cwd_keeps_current_dir_but_projects_file_workspace_root_to_repo_root(
    tmp_path,
) -> None:
    runtime = AgentCliRuntime()
    repo_root = tmp_path / "repo"
    nested = repo_root / "cli"
    nested.mkdir(parents=True)
    _make_git_marker(repo_root / ".git")

    runtime.set_cwd(nested)

    assert Path(runtime.tools.WORKSPACE_ROOT) == nested.resolve()
    assert Path(runtime.tools.PROJECT_ROOT) == repo_root.resolve()
    assert runtime.thread_workspace_context is not None
    assert Path(runtime.thread_workspace_context.cwd) == nested.resolve()
    assert Path(runtime.thread_workspace_context.workspace_root) == repo_root.resolve()


def test_runtime_apply_patch_uses_project_root_file_boundary_from_nested_cwd(tmp_path) -> None:
    runtime = AgentCliRuntime(runtime_policy=RuntimePolicy(approval_policy="never"))
    repo_root = tmp_path / "repo"
    nested = repo_root / "cli"
    nested.mkdir(parents=True)
    _make_git_marker(repo_root / ".git")

    runtime.set_cwd(nested)

    patch_text = "\n".join(
        [
            "*** Begin Patch",
            f"*** Add File: {repo_root / 'AENGTHUB.md'}",
            "+# Demo",
            "*** End Patch",
            "",
        ]
    )
    result = run_command_text_result(runtime, f"/apply_patch {shlex.quote(patch_text)}")

    assert result.tool_events
    assert result.tool_events[-1].ok is True
    assert (repo_root / "AENGTHUB.md").read_text(encoding="utf-8") == "# Demo\n"
    assert Path(result.tool_events[-1].payload["workspace_root"]) == repo_root.resolve()


def test_runtime_set_cwd_ignores_empty_parent_git_marker(tmp_path) -> None:
    runtime = AgentCliRuntime()
    parent = tmp_path / "parent"
    workspace = parent / "workspace"
    workspace.mkdir(parents=True)
    (parent / ".git").mkdir()

    runtime.set_cwd(workspace)

    assert Path(runtime.tools.WORKSPACE_ROOT) == workspace.resolve()
    assert Path(runtime.tools.PROJECT_ROOT) == workspace.resolve()


def test_patch_approval_writes_to_workspace_when_parent_git_marker_is_invalid(tmp_path) -> None:
    parent = tmp_path / "parent"
    workspace = parent / "workspace"
    workspace.mkdir(parents=True)
    (parent / ".git").mkdir()
    runtime = AgentCliRuntime(
        gateway_state_store=InMemoryGatewayStateStore(),
        runtime_policy=RuntimePolicy.normalized(
            approval_policy="on-request",
            sandbox_mode="workspace-write",
        ),
    )
    runtime.set_cwd(workspace)
    patch_text = json.dumps(
        {
            "operation": "file_write",
            "file_path": "approval_probe.txt",
            "content": "approval ok\n",
            "guard_profile": "claude_write",
            "source_tool_name": "Write",
        }
    )

    event = runtime.request_patch_approval(patch_text)
    response = runtime._decide_patch_approval(
        event.payload["approval_id"],
        approved=True,
        decided_by="test",
    )

    assert (workspace / "approval_probe.txt").read_text(encoding="utf-8") == "approval ok\n"
    assert not (parent / "approval_probe.txt").exists()
    assert response["action_result"]["output"]["workspace_root"] == str(workspace.resolve())
