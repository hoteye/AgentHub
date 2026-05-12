from __future__ import annotations

from pathlib import Path

from cli.agent_cli.runtime_workspace.context import (
    create_thread_workspace_context,
    inherit_thread_workspace_context,
    override_thread_workspace_context,
)


def test_create_thread_workspace_context_normalizes_core_fields(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    cwd = root / "cwd"
    cwd.mkdir()
    context = create_thread_workspace_context(
        thread_id="t1",
        cwd=str(cwd),
        workspace_root=str(root),
        approval_policy="ON-REQUEST",
        sandbox_mode="WORKSPACE-WRITE",
        network_access_enabled="enabled",
        web_search_mode="LIVE",
    )
    assert context.thread_id == "t1"
    assert context.cwd == str(cwd.resolve())
    assert context.workspace_root == str(root.resolve())
    assert context.approval_policy == "on-request"
    assert context.sandbox_mode == "workspace-write"
    assert context.network_access_enabled is True
    assert context.web_search_mode == "live"
    assert context.runtime_cwd_source == "runtime_cwd"
    assert context.workspace_root_source == "thread_workspace"
    assert context.policy_source == "runtime_policy"


def test_inherit_thread_workspace_context_keeps_policy_and_can_change_cwd(tmp_path: Path) -> None:
    parent_cwd = tmp_path / "parent"
    parent_cwd.mkdir()
    child_cwd = tmp_path / "child"
    child_cwd.mkdir()
    parent = create_thread_workspace_context(
        thread_id="parent-thread",
        cwd=str(parent_cwd),
        approval_policy="on-failure",
        sandbox_mode="read-only",
        web_search_mode="cached",
    )
    child = inherit_thread_workspace_context(parent, thread_id="child-thread", cwd=str(child_cwd))
    assert child.thread_id == "child-thread"
    assert child.cwd == str(child_cwd.resolve())
    assert child.approval_policy == "on-failure"
    assert child.sandbox_mode == "read-only"
    assert child.web_search_mode == "cached"
    assert child.runtime_cwd_source == "runtime_cwd"
    assert child.workspace_root_source == "inherited"
    assert child.policy_source == "inherited"


def test_override_thread_workspace_context_updates_selected_fields_only(tmp_path: Path) -> None:
    cwd = tmp_path / "base"
    cwd.mkdir()
    context = create_thread_workspace_context(
        thread_id="t2",
        cwd=str(cwd),
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        network_access_enabled=False,
        web_search_mode="cached",
    )
    updated = override_thread_workspace_context(
        context,
        approval_policy="never",
        sandbox_mode="danger-full-access",
        network_access_enabled=True,
    )
    assert updated.thread_id == context.thread_id
    assert updated.cwd == context.cwd
    assert updated.workspace_root == context.workspace_root
    assert updated.approval_policy == "never"
    assert updated.sandbox_mode == "danger-full-access"
    assert updated.network_access_enabled is True
    assert updated.web_search_mode == "cached"
    assert updated.runtime_cwd_source == "runtime_cwd"
    assert updated.workspace_root_source == "runtime_cwd"
    assert updated.policy_source == "runtime_policy"
