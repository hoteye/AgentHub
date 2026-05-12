from __future__ import annotations

from pathlib import Path

from cli.agent_cli import runtime_context_runtime
from cli.agent_cli import runtime_runtime_state_runtime


class _Policy:
    def __init__(
        self,
        *,
        approval_policy: str = "on-request",
        sandbox_mode: str = "workspace-write",
        network_access_enabled: bool | None = None,
        web_search_mode: str | None = None,
    ) -> None:
        self.approval_policy = approval_policy
        self.sandbox_mode = sandbox_mode
        self.network_access_enabled = network_access_enabled
        self.web_search_mode = web_search_mode


def test_runtime_workspace_context_builds_from_thread_cwd_and_policy(tmp_path: Path) -> None:
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    policy = _Policy(
        approval_policy="never",
        sandbox_mode="read-only",
        network_access_enabled=True,
        web_search_mode="live",
    )

    context = runtime_runtime_state_runtime.runtime_workspace_context_state(
        thread_id="thread-01",
        cwd=str(cwd),
        runtime_policy=policy,
        build_runtime_workspace_context_fn=runtime_context_runtime.build_runtime_workspace_context,
    )

    assert context.thread_id == "thread-01"
    assert context.cwd == str(cwd.resolve())
    assert context.workspace_root == str(cwd.resolve())
    assert context.approval_policy == "never"
    assert context.sandbox_mode == "read-only"
    assert context.network_access_enabled is True
    assert context.web_search_mode == "live"
    assert context.runtime_cwd_source == "runtime_cwd"
    assert context.workspace_root_source == "runtime_cwd"
    assert context.policy_source == "runtime_policy"


def test_runtime_workspace_context_refresh_after_cwd_and_policy_change(tmp_path: Path) -> None:
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    context = runtime_context_runtime.build_runtime_workspace_context(
        thread_id="thread-02",
        cwd=str(cwd),
        runtime_policy={
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access_enabled": False,
            "web_search_mode": "cached",
        },
    )

    next_cwd = tmp_path / "next-workspace"
    next_cwd.mkdir()
    refreshed_cwd = runtime_runtime_state_runtime.runtime_workspace_context_after_cwd_change(
        context,
        cwd=str(next_cwd),
        refresh_workspace_context_for_cwd_fn=runtime_context_runtime.refresh_workspace_context_for_cwd,
    )
    assert refreshed_cwd is not None
    assert refreshed_cwd.cwd == str(next_cwd.resolve())
    assert refreshed_cwd.approval_policy == "on-request"
    assert refreshed_cwd.sandbox_mode == "workspace-write"
    assert refreshed_cwd.runtime_cwd_source == "runtime_cwd"
    assert refreshed_cwd.workspace_root_source == "inherited"
    assert refreshed_cwd.policy_source == "runtime_policy"

    refreshed_policy = runtime_runtime_state_runtime.runtime_workspace_context_after_policy_change(
        refreshed_cwd,
        runtime_policy=_Policy(
            approval_policy="on-failure",
            sandbox_mode="danger-full-access",
            network_access_enabled=True,
            web_search_mode="disabled",
        ),
        refresh_workspace_context_for_runtime_policy_fn=runtime_context_runtime.refresh_workspace_context_for_runtime_policy,
    )
    assert refreshed_policy is not None
    assert refreshed_policy.cwd == str(next_cwd.resolve())
    assert refreshed_policy.approval_policy == "on-failure"
    assert refreshed_policy.sandbox_mode == "danger-full-access"
    assert refreshed_policy.network_access_enabled is True
    assert refreshed_policy.web_search_mode == "disabled"
    assert refreshed_policy.runtime_cwd_source == "runtime_cwd"
    assert refreshed_policy.workspace_root_source == "inherited"
    assert refreshed_policy.policy_source == "runtime_policy"


def test_runtime_workspace_context_after_thread_resume_rebuilds_for_new_thread_and_keeps_workspace_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    old_cwd = root / "workspace-a"
    old_cwd.mkdir()
    next_cwd = root / "workspace-b"
    next_cwd.mkdir()

    context = runtime_context_runtime.build_runtime_workspace_context(
        thread_id="thread-old",
        cwd=str(old_cwd),
        workspace_root=str(root),
        runtime_policy={
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access_enabled": False,
            "web_search_mode": "cached",
        },
    )

    resumed = runtime_runtime_state_runtime.runtime_workspace_context_after_thread_resume(
        context,
        thread_id="thread-new",
        cwd=str(next_cwd),
        runtime_policy=_Policy(
            approval_policy="never",
            sandbox_mode="read-only",
            network_access_enabled=True,
            web_search_mode="live",
        ),
        workspace_root=str(root),
        build_runtime_workspace_context_fn=runtime_context_runtime.build_runtime_workspace_context,
        refresh_workspace_context_for_cwd_fn=runtime_context_runtime.refresh_workspace_context_for_cwd,
        refresh_workspace_context_for_runtime_policy_fn=runtime_context_runtime.refresh_workspace_context_for_runtime_policy,
    )

    assert resumed.thread_id == "thread-new"
    assert resumed.cwd == str(next_cwd.resolve())
    assert resumed.workspace_root == str(root.resolve())
    assert resumed.approval_policy == "never"
    assert resumed.sandbox_mode == "read-only"
    assert resumed.network_access_enabled is True
    assert resumed.web_search_mode == "live"
    assert resumed.runtime_cwd_source == "runtime_cwd"
    assert resumed.workspace_root_source == "thread_workspace"
    assert resumed.policy_source == "runtime_policy"


def test_runtime_workspace_context_after_thread_resume_same_thread_refreshes_cwd_and_policy_sources(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    old_cwd = root / "workspace-a"
    old_cwd.mkdir()
    next_cwd = root / "workspace-b"
    next_cwd.mkdir()

    context = runtime_context_runtime.build_runtime_workspace_context(
        thread_id="thread-same",
        cwd=str(old_cwd),
        workspace_root=str(root),
        runtime_policy={
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access_enabled": False,
            "web_search_mode": "cached",
        },
    )

    resumed = runtime_runtime_state_runtime.runtime_workspace_context_after_thread_resume(
        context,
        thread_id="thread-same",
        cwd=str(next_cwd),
        runtime_policy=_Policy(
            approval_policy="on-failure",
            sandbox_mode="danger-full-access",
            network_access_enabled=True,
            web_search_mode="disabled",
        ),
        workspace_root=str(root),
        build_runtime_workspace_context_fn=runtime_context_runtime.build_runtime_workspace_context,
        refresh_workspace_context_for_cwd_fn=runtime_context_runtime.refresh_workspace_context_for_cwd,
        refresh_workspace_context_for_runtime_policy_fn=runtime_context_runtime.refresh_workspace_context_for_runtime_policy,
    )

    assert resumed.thread_id == "thread-same"
    assert resumed.cwd == str(next_cwd.resolve())
    assert resumed.workspace_root == str(root.resolve())
    assert resumed.approval_policy == "on-failure"
    assert resumed.sandbox_mode == "danger-full-access"
    assert resumed.network_access_enabled is True
    assert resumed.web_search_mode == "disabled"
    assert resumed.runtime_cwd_source == "runtime_cwd"
    assert resumed.workspace_root_source == "thread_workspace"
    assert resumed.policy_source == "runtime_policy"
