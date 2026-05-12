from __future__ import annotations

from . import resolution
from .models import ThreadWorkspaceContext


def create_thread_workspace_context(
    *,
    thread_id: str,
    cwd: str,
    workspace_root: str | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
    web_search_mode: str | None = None,
) -> ThreadWorkspaceContext:
    resolved_cwd = resolution.normalize_runtime_cwd(str(cwd))
    resolved_workspace_root, workspace_root_source = resolution.resolve_workspace_root_with_source(
        cwd=resolved_cwd,
        workspace_root=workspace_root,
    )
    return ThreadWorkspaceContext(
        thread_id=str(thread_id),
        cwd=resolved_cwd,
        workspace_root=resolved_workspace_root,
        approval_policy=resolution.normalize_approval_policy(approval_policy),
        sandbox_mode=resolution.normalize_sandbox_mode(sandbox_mode),
        network_access_enabled=resolution.normalize_network_access(network_access_enabled),
        web_search_mode=resolution.normalize_web_search_mode(web_search_mode),
        runtime_cwd_source="runtime_cwd",
        workspace_root_source=workspace_root_source,
        policy_source="runtime_policy",
    )


def inherit_thread_workspace_context(
    parent: ThreadWorkspaceContext,
    *,
    thread_id: str,
    cwd: str | None = None,
    workspace_root: str | None = None,
) -> ThreadWorkspaceContext:
    resolved_cwd = resolution.normalize_runtime_cwd(cwd or parent.cwd)
    inherited_workspace_root = workspace_root if workspace_root is not None else parent.workspace_root
    resolved_workspace_root, workspace_root_source = resolution.resolve_workspace_root_with_source(
        cwd=resolved_cwd,
        workspace_root=inherited_workspace_root,
        inherited=workspace_root is None,
    )
    return parent.with_overrides(
        thread_id=str(thread_id),
        cwd=resolved_cwd,
        workspace_root=resolved_workspace_root,
        runtime_cwd_source="runtime_cwd" if cwd is not None else "inherited",
        workspace_root_source=workspace_root_source,
        policy_source="inherited",
    )


def override_thread_workspace_context(
    context: ThreadWorkspaceContext,
    *,
    cwd: str | None = None,
    workspace_root: str | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
    web_search_mode: str | None = None,
) -> ThreadWorkspaceContext:
    policy_updated = any(
        value is not None
        for value in (
            approval_policy,
            sandbox_mode,
            network_access_enabled,
            web_search_mode,
        )
    )
    next_cwd = resolution.normalize_runtime_cwd(cwd or context.cwd)
    if workspace_root is None:
        next_workspace_root = resolution.resolve_workspace_root(
            cwd=next_cwd,
            workspace_root=context.workspace_root,
        )
        workspace_root_source = (
            "inherited"
            if cwd is not None
            else resolution.normalize_workspace_root_source(getattr(context, "workspace_root_source", None))
        )
    else:
        next_workspace_root, workspace_root_source = resolution.resolve_workspace_root_with_source(
            cwd=next_cwd,
            workspace_root=workspace_root,
        )
    return context.with_overrides(
        cwd=next_cwd,
        workspace_root=next_workspace_root,
        approval_policy=resolution.normalize_approval_policy(approval_policy)
        if approval_policy is not None
        else None,
        sandbox_mode=resolution.normalize_sandbox_mode(sandbox_mode)
        if sandbox_mode is not None
        else None,
        network_access_enabled=resolution.normalize_network_access(network_access_enabled)
        if network_access_enabled is not None
        else None,
        web_search_mode=resolution.normalize_web_search_mode(web_search_mode)
        if web_search_mode is not None
        else None,
        runtime_cwd_source=(
            "runtime_cwd"
            if cwd is not None
            else resolution.normalize_runtime_cwd_source(getattr(context, "runtime_cwd_source", None))
        ),
        workspace_root_source=workspace_root_source,
        policy_source=(
            "runtime_policy"
            if policy_updated
            else resolution.normalize_policy_source(getattr(context, "policy_source", None))
        ),
    )
