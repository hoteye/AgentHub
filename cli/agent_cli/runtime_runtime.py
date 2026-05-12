from cli.agent_cli import runtime_runtime_helpers as runtime_runtime_helpers

preview_text = runtime_runtime_helpers.preview_text
runtime_now_iso = runtime_runtime_helpers.runtime_now_iso
resolve_runtime_cwd = runtime_runtime_helpers.resolve_runtime_cwd
set_tools_workspace_root = runtime_runtime_helpers.set_tools_workspace_root
response_runtime_snapshot = runtime_runtime_helpers.response_runtime_snapshot
describe_thread_fallback = runtime_runtime_helpers.describe_thread_fallback
runtime_policy_override_payload = runtime_runtime_helpers.runtime_policy_override_payload
context_snapshot_overrides = runtime_runtime_helpers.context_snapshot_overrides
configure_runtime_tool_hooks = runtime_runtime_helpers.configure_runtime_tool_hooks
runtime_state_defaults = runtime_runtime_helpers.runtime_state_defaults
approval_list_event = runtime_runtime_helpers.approval_list_event
configure_model_selection = runtime_runtime_helpers.configure_model_selection
configure_named_selection = runtime_runtime_helpers.configure_named_selection
approval_list_rows = runtime_runtime_helpers.approval_list_rows
slash_command_rows = runtime_runtime_helpers.slash_command_rows
shell_approval_response = runtime_runtime_helpers.shell_approval_response
begin_shell_request = runtime_runtime_helpers.begin_shell_request
decide_approval = runtime_runtime_helpers.decide_approval
build_local_plan = runtime_runtime_helpers.build_local_plan
preview_local_plan = runtime_runtime_helpers.preview_local_plan
local_plan_attempt_state = runtime_runtime_helpers.local_plan_attempt_state
local_plan_preview_state = runtime_runtime_helpers.local_plan_preview_state
normalized_planner_input_item = runtime_runtime_helpers.normalized_planner_input_item


def apply_runtime_policy(
    *,
    runtime_policy,
    approval_policy,
    sandbox_mode,
    web_search_mode,
    network_access_enabled,
    agent_runtime_policy_setter,
):
    return runtime_runtime_helpers.apply_runtime_policy(
        runtime_policy=runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        agent_runtime_policy_setter=agent_runtime_policy_setter,
        runtime_policy_override_payload_fn=runtime_policy_override_payload,
    )


def configure_runtime_policy_state(
    *,
    runtime_policy,
    approval_policy,
    sandbox_mode,
    web_search_mode,
    network_access_enabled,
    agent_runtime_policy_setter,
):
    return runtime_runtime_helpers.configure_runtime_policy_state(
        runtime_policy=runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        apply_runtime_policy_fn=apply_runtime_policy,
        agent_runtime_policy_setter=agent_runtime_policy_setter,
    )


def bootstrap_runtime_environment(
    *,
    tools,
    agent,
    runtime_policy,
    shell_activity_callback,
    shell_activity_suppressed_getter,
    shell_cancel_event_getter,
    resolve_runtime_cwd_fn,
    set_tools_workspace_root_fn,
    runtime_policy_status_getter=None,
    request_patch_approval_fn=None,
):
    return runtime_runtime_helpers.bootstrap_runtime_environment(
        tools=tools,
        agent=agent,
        runtime_policy=runtime_policy,
        configure_runtime_tool_hooks_fn=configure_runtime_tool_hooks,
        runtime_policy_override_payload_fn=runtime_policy_override_payload,
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
    cwd,
    resolve_runtime_cwd_fn,
    set_tools_workspace_root_fn,
    agent_setter,
):
    return runtime_runtime_helpers.apply_runtime_cwd(
        cwd=cwd,
        resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
        set_tools_workspace_root_fn=set_tools_workspace_root_fn,
        agent_setter=agent_setter,
    )


def runtime_cwd_state(
    *,
    cwd,
    resolve_runtime_cwd_fn,
    set_tools_workspace_root_fn,
    agent_setter,
):
    return runtime_runtime_helpers.runtime_cwd_state(
        cwd=cwd,
        apply_runtime_cwd_fn=apply_runtime_cwd,
        resolve_runtime_cwd_fn=resolve_runtime_cwd_fn,
        set_tools_workspace_root_fn=set_tools_workspace_root_fn,
        agent_setter=agent_setter,
    )


def configure_delegate_selection(
    *,
    agent,
    role_name,
    model,
    provider,
    reasoning_effort,
    timeout,
    clear,
    cleanup_delegated_sessions_for_role_fn,
):
    return runtime_runtime_helpers.configure_delegate_selection(
        agent=agent,
        role_name=role_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
        configure_named_selection_fn=configure_named_selection,
        cleanup_delegated_sessions_for_role_fn=cleanup_delegated_sessions_for_role_fn,
    )


def runtime_init_state(
    *,
    threading_module,
    thread_store,
    run_command_text_result_fn,
    interrupt_requested_fn,
    interrupt_result_fn,
    runtime_owner=None,
):
    return runtime_runtime_helpers.runtime_init_state(
        threading_module=threading_module,
        thread_store=thread_store,
        run_command_text_result_fn=run_command_text_result_fn,
        interrupt_requested_fn=interrupt_requested_fn,
        interrupt_result_fn=interrupt_result_fn,
        runtime_owner=runtime_owner,
        runtime_state_defaults_fn=runtime_state_defaults,
    )


def local_plan_state_update(
    *,
    text,
    last_plan,
    last_plan_text,
    build_local_plan_fn,
    preview,
):
    return runtime_runtime_helpers.local_plan_state_update(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
        preview=preview,
        local_plan_preview_state_fn=local_plan_preview_state,
        local_plan_attempt_state_fn=local_plan_attempt_state,
    )
