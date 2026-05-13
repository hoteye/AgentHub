from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_workspace.models import ThreadWorkspaceContext


def configure_runtime_policy_state(
    *,
    runtime_policy: Any,
    approval_policy: str | None,
    sandbox_mode: str | None,
    web_search_mode: str | None,
    network_access_enabled: str | bool | None,
    apply_runtime_policy_fn: Callable[..., Any],
    agent_runtime_policy_setter: Callable[[dict[str, Any]], Any] | None,
) -> tuple[Any, dict[str, str]]:
    updated_policy = apply_runtime_policy_fn(
        runtime_policy=runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        agent_runtime_policy_setter=agent_runtime_policy_setter,
    )
    return updated_policy, updated_policy.to_status()


def context_snapshot_overrides(
    *,
    environment_snapshot: dict[str, Any] | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        dict(environment_snapshot or {}) if isinstance(environment_snapshot, dict) else {},
        dict(workspace_snapshot or {}) if isinstance(workspace_snapshot, dict) else {},
    )


def bootstrap_runtime_environment(
    *,
    tools: Any,
    agent: Any,
    runtime_policy: Any,
    configure_runtime_tool_hooks_fn: Callable[..., None],
    runtime_policy_override_payload_fn: Callable[[Any], dict[str, Any]],
    resolve_runtime_cwd_fn: Callable[[Any], Path],
    set_tools_workspace_root_fn: Callable[[Path], Path],
    shell_activity_callback: Callable[..., Any],
    shell_activity_suppressed_getter: Callable[..., Any],
    shell_cancel_event_getter: Callable[..., Any],
    runtime_policy_status_getter: Callable[..., Any] | None = None,
    request_patch_approval_fn: Callable[..., Any] | None = None,
) -> Path:
    defer_planner_reload = getattr(agent, "defer_planner_reload", None)
    planner_reload_context = (
        defer_planner_reload() if callable(defer_planner_reload) else nullcontext()
    )
    with planner_reload_context:
        agent_runtime_policy_setter = getattr(agent, "set_runtime_policy_overrides", None)
        if callable(agent_runtime_policy_setter):
            agent_runtime_policy_setter(runtime_policy_override_payload_fn(runtime_policy))
        configure_runtime_tool_hooks_fn(
            tools=tools,
            shell_activity_callback=shell_activity_callback,
            shell_activity_suppressed_getter=shell_activity_suppressed_getter,
            shell_cancel_event_getter=shell_cancel_event_getter,
            runtime_policy_status_getter=runtime_policy_status_getter,
            request_patch_approval_fn=request_patch_approval_fn,
        )
        runtime_cwd = resolve_runtime_cwd_fn(
            getattr(tools, "WORKSPACE_ROOT", None) or getattr(tools, "PROJECT_ROOT", None)
        )
        runtime_cwd = set_tools_workspace_root_fn(runtime_cwd)
        agent_plugin_factory_setter = getattr(agent, "set_plugin_manager_factory", None)
        agent_lazy_pending = getattr(agent, "_planner", None) is None and bool(
            getattr(agent, "_planner_lazy_enabled", False)
        )
        if agent_lazy_pending:
            agent._plugin_manager_factory = lambda: getattr(tools, "_plugin_manager", None)
            agent.cwd = runtime_cwd
        else:
            if callable(agent_plugin_factory_setter):
                agent_plugin_factory_setter(lambda: getattr(tools, "_plugin_manager", None))
            agent_setter = getattr(agent, "set_cwd", None)
            if callable(agent_setter):
                runtime_cwd = Path(agent_setter(runtime_cwd)).resolve()
        return runtime_cwd


def runtime_cwd_state(
    *,
    cwd: str | Path,
    apply_runtime_cwd_fn: Callable[..., Path],
    resolve_runtime_cwd_fn: Callable[[Any], Path],
    set_tools_workspace_root_fn: Callable[[Path], Path],
    agent_setter: Callable[[Path], Any] | None,
) -> tuple[Path, dict[str, Any]]:
    if callable(agent_setter):
        defer_planner_reload = getattr(
            getattr(agent_setter, "__self__", None), "defer_planner_reload", None
        )
        planner_reload_context = (
            defer_planner_reload() if callable(defer_planner_reload) else nullcontext()
        )
    else:
        planner_reload_context = nullcontext()
    with planner_reload_context:
        runtime_cwd = apply_runtime_cwd_fn(
            cwd=cwd,
            resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
            set_tools_workspace_root_fn=set_tools_workspace_root_fn,
            agent_setter=agent_setter,
        )
    return runtime_cwd, {
        "_background_task_adapter_cache": None,
        "_background_task_adapter_cwd": "",
        "_orchestration_runtime_services_cache": None,
        "_orchestration_runtime_services_cwd": "",
    }


def configure_delegate_selection(
    *,
    agent: Any,
    role_name: str,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    clear: bool,
    configure_named_selection_fn: Callable[..., dict[str, Any]],
    cleanup_delegated_sessions_for_role_fn: Callable[[str], Any],
) -> dict[str, Any]:
    result = dict(
        configure_named_selection_fn(
            agent=agent,
            configurator_name="configure_delegate_selection",
            disabled_error="delegation override switch disabled",
            target_name=role_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )
    )
    cleanup_delegated_sessions_for_role_fn(role_name)
    return result


def local_plan_state_update(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
    preview: bool,
    local_plan_preview_state_fn: Callable[..., tuple[dict[str, Any], dict[str, Any], str]],
    local_plan_attempt_state_fn: Callable[..., tuple[dict[str, Any], str, bool]],
) -> tuple[dict[str, Any], dict[str, Any], str, bool]:
    if preview:
        payload, cached_plan, cached_text = local_plan_preview_state_fn(
            text=text,
            last_plan=last_plan,
            last_plan_text=last_plan_text,
            build_local_plan_fn=build_local_plan_fn,
        )
        return payload, cached_plan, cached_text, False
    cached_plan, cached_text, allowed = local_plan_attempt_state_fn(
        text=text,
        build_local_plan_fn=build_local_plan_fn,
    )
    return cached_plan, cached_plan, cached_text, allowed


def runtime_workspace_context_state(
    *,
    thread_id: str | None,
    cwd: str | Path,
    runtime_policy: Any,
    workspace_root: str | None = None,
    build_runtime_workspace_context_fn: Callable[..., ThreadWorkspaceContext],
) -> ThreadWorkspaceContext:
    return build_runtime_workspace_context_fn(
        thread_id=thread_id,
        cwd=cwd,
        runtime_policy=runtime_policy,
        workspace_root=workspace_root,
    )


def runtime_workspace_context_after_cwd_change(
    context: ThreadWorkspaceContext | None,
    *,
    cwd: str | Path,
    workspace_root: str | None = None,
    refresh_workspace_context_for_cwd_fn: Callable[..., ThreadWorkspaceContext | None],
) -> ThreadWorkspaceContext | None:
    return refresh_workspace_context_for_cwd_fn(
        context,
        cwd=cwd,
        workspace_root=workspace_root,
    )


def runtime_workspace_context_after_policy_change(
    context: ThreadWorkspaceContext | None,
    *,
    runtime_policy: Any,
    refresh_workspace_context_for_runtime_policy_fn: Callable[..., ThreadWorkspaceContext | None],
) -> ThreadWorkspaceContext | None:
    return refresh_workspace_context_for_runtime_policy_fn(
        context,
        runtime_policy=runtime_policy,
    )


def runtime_workspace_context_after_thread_resume(
    context: ThreadWorkspaceContext | None,
    *,
    thread_id: str | None,
    cwd: str | Path,
    runtime_policy: Any,
    workspace_root: str | None = None,
    build_runtime_workspace_context_fn: Callable[..., ThreadWorkspaceContext],
    refresh_workspace_context_for_cwd_fn: Callable[..., ThreadWorkspaceContext | None],
    refresh_workspace_context_for_runtime_policy_fn: Callable[..., ThreadWorkspaceContext | None],
) -> ThreadWorkspaceContext:
    normalized_thread_id = str(thread_id or "")
    if context is None or str(getattr(context, "thread_id", "") or "") != normalized_thread_id:
        return build_runtime_workspace_context_fn(
            thread_id=normalized_thread_id,
            cwd=cwd,
            runtime_policy=runtime_policy,
            workspace_root=workspace_root,
        )
    refreshed_cwd = refresh_workspace_context_for_cwd_fn(
        context,
        cwd=cwd,
        workspace_root=workspace_root,
    )
    if refreshed_cwd is None:
        refreshed_cwd = build_runtime_workspace_context_fn(
            thread_id=normalized_thread_id,
            cwd=cwd,
            runtime_policy=runtime_policy,
            workspace_root=workspace_root,
        )
    refreshed_policy = refresh_workspace_context_for_runtime_policy_fn(
        refreshed_cwd,
        runtime_policy=runtime_policy,
    )
    if refreshed_policy is None:
        return build_runtime_workspace_context_fn(
            thread_id=normalized_thread_id,
            cwd=cwd,
            runtime_policy=runtime_policy,
            workspace_root=workspace_root,
        )
    return refreshed_policy
