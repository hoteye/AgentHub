from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import runtime_context_runtime as runtime_context_runtime_service
from cli.agent_cli import runtime_runtime_state_runtime as runtime_state_runtime_service


def runtime_delegated_binding_kwargs(
    *,
    session_class: Any,
    now_iso_fn: Callable[..., Any],
    preview_text_fn: Callable[..., Any],
    build_background_task_adapter_fn: Callable[..., Any],
    build_planner_fn: Callable[..., Any],
    current_host_platform_fn: Callable[..., Any],
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> dict[str, Any]:
    return {
        "session_class": session_class,
        "now_iso_fn": now_iso_fn,
        "preview_text_fn": preview_text_fn,
        "build_background_task_adapter_fn": build_background_task_adapter_fn,
        "build_planner_fn": build_planner_fn,
        "current_host_platform_fn": current_host_platform_fn,
        "max_active": max_active,
        "read_only_max_active": read_only_max_active,
        "long_running_max_active": long_running_max_active,
    }


def runtime_delegated_api_binding_kwargs(*, session_class: Any) -> dict[str, Any]:
    return {"session_class": session_class}


def runtime_policy_gateway_binding_kwargs(
    *,
    cli_version: str,
    local_approval_connector_key: str,
    local_approval_plugin_name: str,
    local_patch_approval_reason: str,
    local_background_teammate_approval_reason: str,
    slash_command_specs_fn: Callable[..., Any],
    match_slash_commands_fn: Callable[..., Any],
    autocomplete_slash_command_fn: Callable[..., Any],
    github_action_artifact_refs_fn: Callable[..., Any],
    find_github_workflow_run_fn: Callable[..., Any],
) -> dict[str, Any]:
    return {
        "cli_version": cli_version,
        "local_approval_connector_key": local_approval_connector_key,
        "local_approval_plugin_name": local_approval_plugin_name,
        "local_patch_approval_reason": local_patch_approval_reason,
        "local_background_teammate_approval_reason": local_background_teammate_approval_reason,
        "slash_command_specs_fn": slash_command_specs_fn,
        "match_slash_commands_fn": match_slash_commands_fn,
        "autocomplete_slash_command_fn": autocomplete_slash_command_fn,
        "github_action_artifact_refs_fn": github_action_artifact_refs_fn,
        "find_github_workflow_run_fn": find_github_workflow_run_fn,
    }


def runtime_shell_binding_kwargs(
    *,
    trace_fn: Callable[..., Any],
    preview_text_fn: Callable[..., Any],
    connector_key: str,
    plugin_name: str,
    approval_reason: str,
) -> dict[str, Any]:
    return {
        "trace": trace_fn,
        "preview_text": preview_text_fn,
        "connector_key": connector_key,
        "plugin_name": plugin_name,
        "approval_reason": approval_reason,
    }


def resume_thread_workspace_context(
    *,
    tools: Any,
    thread_workspace_context: Any,
    thread_id: str | None,
    cwd: Any,
    runtime_policy: Any,
) -> Any:
    workspace_root = str(runtime_context_runtime_service.tools_file_workspace_root(tools=tools))
    return runtime_state_runtime_service.runtime_workspace_context_after_thread_resume(
        thread_workspace_context,
        thread_id=thread_id,
        cwd=cwd,
        runtime_policy=runtime_policy,
        workspace_root=workspace_root,
        build_runtime_workspace_context_fn=runtime_context_runtime_service.build_runtime_workspace_context,
        refresh_workspace_context_for_cwd_fn=runtime_context_runtime_service.refresh_workspace_context_for_cwd,
        refresh_workspace_context_for_runtime_policy_fn=runtime_context_runtime_service.refresh_workspace_context_for_runtime_policy,
    )


__all__ = [
    "resume_thread_workspace_context",
    "runtime_delegated_api_binding_kwargs",
    "runtime_delegated_binding_kwargs",
    "runtime_policy_gateway_binding_kwargs",
    "runtime_shell_binding_kwargs",
]
