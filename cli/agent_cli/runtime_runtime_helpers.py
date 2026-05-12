from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cli.agent_cli import runtime_context_runtime
from cli.agent_cli import runtime_planner_runtime
from cli.agent_cli import runtime_runtime_facade_runtime
from cli.agent_cli import runtime_runtime_state_runtime
from cli.agent_cli import runtime_shell_runtime
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import build_local_plan
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import local_plan_attempt_state
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import local_plan_preview_state
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import local_plan_state_update
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import normalized_planner_input_item
from cli.agent_cli.runtime_runtime_helpers_local_plan_runtime import preview_local_plan


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    return runtime_context_runtime.preview_text(value, max_chars=max_chars)


def runtime_now_iso() -> str:
    return runtime_context_runtime.runtime_now_iso()


def resolve_runtime_cwd(value: Any | None) -> Path:
    return runtime_context_runtime.resolve_runtime_cwd(value)


def set_tools_workspace_root(*, tools: Any, path: Path) -> Path:
    return runtime_context_runtime.set_tools_workspace_root(tools=tools, path=path)


def response_runtime_snapshot(*, cwd: Any, provider_status: dict[str, Any], runtime_policy: dict[str, Any]) -> dict[str, Any]:
    return runtime_context_runtime.response_runtime_snapshot(
        cwd=cwd,
        provider_status=provider_status,
        runtime_policy=runtime_policy,
    )


def describe_thread_fallback(
    *,
    thread: dict[str, Any] | None,
    thread_id: str | None,
    thread_name: str,
    cwd: Any,
    turns: list[dict[str, Any]] | None,
    normalized_status: str,
    provider_status: dict[str, Any],
    runtime_policy: dict[str, Any],
    metadata_overrides: dict[str, Any] | None,
    cli_version: str,
) -> dict[str, Any]:
    return runtime_context_runtime.describe_thread_fallback(
        thread=thread,
        thread_id=thread_id,
        thread_name=thread_name,
        cwd=cwd,
        turns=turns,
        normalized_status=normalized_status,
        provider_status=provider_status,
        runtime_policy=runtime_policy,
        metadata_overrides=metadata_overrides,
        cli_version=cli_version,
    )


def apply_runtime_policy(
    *,
    runtime_policy: Any,
    approval_policy: str | None,
    sandbox_mode: str | None,
    web_search_mode: str | None,
    network_access_enabled: str | bool | None,
    agent_runtime_policy_setter: Callable[[dict[str, Any]], Any] | None,
    runtime_policy_override_payload_fn: Callable[[Any], dict[str, Any]],
) -> Any:
    return runtime_context_runtime.apply_runtime_policy(
        runtime_policy=runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        agent_runtime_policy_setter=agent_runtime_policy_setter,
        runtime_policy_override_payload_fn=runtime_policy_override_payload_fn,
    )


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
    return runtime_runtime_state_runtime.configure_runtime_policy_state(
        runtime_policy=runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        apply_runtime_policy_fn=apply_runtime_policy_fn,
        agent_runtime_policy_setter=agent_runtime_policy_setter,
    )


def runtime_policy_override_payload(runtime_policy: Any) -> dict[str, Any]:
    return runtime_context_runtime.runtime_policy_override_payload(runtime_policy)


def context_snapshot_overrides(
    *,
    environment_snapshot: dict[str, Any] | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return runtime_runtime_state_runtime.context_snapshot_overrides(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
    )


def configure_runtime_tool_hooks(
    *,
    tools: Any,
    shell_activity_callback: Callable[..., Any],
    shell_activity_suppressed_getter: Callable[..., Any],
    shell_cancel_event_getter: Callable[..., Any],
    runtime_policy_status_getter: Callable[..., Any] | None = None,
    request_patch_approval_fn: Callable[..., Any] | None = None,
) -> None:
    runtime_context_runtime.configure_runtime_tool_hooks(
        tools=tools,
        shell_activity_callback=shell_activity_callback,
        shell_activity_suppressed_getter=shell_activity_suppressed_getter,
        shell_cancel_event_getter=shell_cancel_event_getter,
        runtime_policy_status_getter=runtime_policy_status_getter,
        request_patch_approval_fn=request_patch_approval_fn,
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
    return runtime_runtime_state_runtime.bootstrap_runtime_environment(
        tools=tools,
        agent=agent,
        runtime_policy=runtime_policy,
        configure_runtime_tool_hooks_fn=configure_runtime_tool_hooks_fn,
        runtime_policy_override_payload_fn=runtime_policy_override_payload_fn,
        resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
        set_tools_workspace_root_fn=set_tools_workspace_root_fn,
        shell_activity_callback=shell_activity_callback,
        shell_activity_suppressed_getter=shell_activity_suppressed_getter,
        shell_cancel_event_getter=shell_cancel_event_getter,
        runtime_policy_status_getter=runtime_policy_status_getter,
        request_patch_approval_fn=request_patch_approval_fn,
    )


def apply_runtime_cwd(
    *,
    cwd: str | Path,
    resolve_runtime_cwd_fn: Callable[[Any], Path],
    set_tools_workspace_root_fn: Callable[[Path], Path],
    agent_setter: Callable[[Path], Any] | None,
) -> Path:
    return runtime_context_runtime.apply_runtime_cwd(
        cwd=cwd,
        resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
        set_tools_workspace_root_fn=set_tools_workspace_root_fn,
        agent_setter=agent_setter,
    )


def runtime_cwd_state(
    *,
    cwd: str | Path,
    apply_runtime_cwd_fn: Callable[..., Path],
    resolve_runtime_cwd_fn: Callable[[Any], Path],
    set_tools_workspace_root_fn: Callable[[Path], Path],
    agent_setter: Callable[[Path], Any] | None,
) -> tuple[Path, dict[str, Any]]:
    return runtime_runtime_state_runtime.runtime_cwd_state(
        cwd=cwd,
        apply_runtime_cwd_fn=apply_runtime_cwd_fn,
        resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
        set_tools_workspace_root_fn=set_tools_workspace_root_fn,
        agent_setter=agent_setter,
    )


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
    return runtime_runtime_state_runtime.configure_delegate_selection(
        agent=agent,
        role_name=role_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
        configure_named_selection_fn=configure_named_selection_fn,
        cleanup_delegated_sessions_for_role_fn=cleanup_delegated_sessions_for_role_fn,
    )


def runtime_state_defaults(*, threading_module: Any) -> dict[str, Any]:
    return runtime_context_runtime.runtime_state_defaults(threading_module=threading_module)


def runtime_init_state(
    *,
    threading_module: Any,
    thread_store: Any,
    run_command_text_result_fn: Callable[[str], Any],
    interrupt_requested_fn: Callable[[], bool],
    interrupt_result_fn: Callable[[], tuple[str, list[Any]]],
    runtime_owner: Any | None = None,
    runtime_state_defaults_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return runtime_runtime_facade_runtime.runtime_init_state(
        threading_module=threading_module,
        thread_store=thread_store,
        run_command_text_result_fn=run_command_text_result_fn,
        interrupt_requested_fn=interrupt_requested_fn,
        interrupt_result_fn=interrupt_result_fn,
        runtime_owner=runtime_owner,
        runtime_state_defaults_fn=runtime_state_defaults_fn,
    )


def approval_list_event(
    *,
    rows: list[dict[str, Any]],
    status: str | None,
    tool_event_factory: Callable[..., Any],
) -> Any:
    return runtime_runtime_facade_runtime.approval_list_event(
        rows=rows,
        status=status,
        tool_event_factory=tool_event_factory,
    )


def configure_model_selection(
    *,
    agent: Any,
    model: str | None,
    reasoning_effort: str | None,
    persist: bool = False,
    write_scope: str | None = None,
) -> dict[str, Any]:
    return runtime_planner_runtime.configure_model_selection(
        agent=agent,
        model=model,
        reasoning_effort=reasoning_effort,
        persist=persist,
        write_scope=write_scope,
    )


def configure_named_selection(
    *,
    agent: Any,
    configurator_name: str,
    disabled_error: str,
    target_name: str,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    clear: bool,
) -> dict[str, Any]:
    return runtime_planner_runtime.configure_named_selection(
        agent=agent,
        configurator_name=configurator_name,
        disabled_error=disabled_error,
        target_name=target_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
    )


def approval_list_rows(
    *,
    tickets: list[Any],
    get_action_request_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    return runtime_runtime_facade_runtime.approval_list_rows(
        tickets=tickets,
        get_action_request_fn=get_action_request_fn,
    )


def slash_command_rows(specs: list[Any]) -> list[dict[str, str]]:
    return runtime_runtime_facade_runtime.slash_command_rows(specs)


def shell_approval_response(**kwargs: Any) -> Any:
    return runtime_shell_runtime.shell_approval_response(**kwargs)


def begin_shell_request(**kwargs: Any) -> dict[str, Any]:
    return runtime_shell_runtime.begin_shell_request(**kwargs)


def decide_approval(**kwargs: Any) -> dict[str, Any]:
    return runtime_shell_runtime.decide_approval(**kwargs)
