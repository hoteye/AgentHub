from __future__ import annotations

from typing import Any, Callable


def build_runtime_build_planner_proxy(
    *,
    get_build_planner_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., Any]:
    def _runtime_build_planner_proxy(*args: Any, **kwargs: Any) -> Any:
        return runtime_pure_helpers_runtime_service.build_planner_proxy(
            *args,
            build_planner_fn=get_build_planner_fn(),
            **kwargs,
        )

    return _runtime_build_planner_proxy


def build_runtime_background_task_adapter_builder_proxy(
    *,
    get_build_background_task_adapter_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[[], Callable[..., Any]]:
    def _runtime_background_task_adapter_builder_proxy() -> Callable[..., Any]:
        return runtime_pure_helpers_runtime_service.background_task_adapter_builder_proxy(
            build_background_task_adapter_fn=get_build_background_task_adapter_fn()
        )

    return _runtime_background_task_adapter_builder_proxy


def build_runtime_background_task_adapter_proxy(
    *,
    get_build_background_task_adapter_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., Any]:
    def _runtime_build_background_task_adapter_proxy(*args: Any, **kwargs: Any) -> Any:
        return runtime_pure_helpers_runtime_service.build_background_task_adapter_proxy(
            *args,
            build_background_task_adapter_fn=get_build_background_task_adapter_fn(),
            **kwargs,
        )

    return _runtime_build_background_task_adapter_proxy


def build_runtime_find_github_workflow_run_proxy(
    *,
    get_find_github_workflow_run_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., Any]:
    def _runtime_find_github_workflow_run_proxy(*args: Any, **kwargs: Any) -> Any:
        return runtime_pure_helpers_runtime_service.find_github_workflow_run_proxy(
            *args,
            find_github_workflow_run_fn=get_find_github_workflow_run_fn(),
            **kwargs,
        )

    return _runtime_find_github_workflow_run_proxy


def initialize_agent_cli_runtime(
    runtime: Any,
    *,
    tools: Any,
    agent: Any,
    activity_callback: Any,
    turn_event_callback: Any,
    thread_store: Any,
    thread_id: Any,
    gateway_state_store: Any,
    action_worker: Any,
    browser_action_executor: Any,
    runtime_policy: Any,
    gateway_broadcaster: Any,
    current_dt_provider: Any,
    tool_registry_cls: Any,
    agent_cls: Any,
    provider_availability_persistence_runtime_service: Any,
    run_manager_cls: Any,
    action_worker_cls: Any,
    gateway_state_store_cls: Any,
    gateway_broadcaster_cls: Any,
    runtime_policy_cls: Any,
    provider_availability_refresh_runtime_service: Any,
    runtime_runtime: Any,
    threading_module: Any,
) -> None:
    runtime.tools = tools or tool_registry_cls()
    runtime.agent = agent or agent_cls()
    runtime.provider_availability_state_path = (
        provider_availability_persistence_runtime_service.provider_availability_state_path()
    )
    runtime._provider_availability_state_path = runtime.provider_availability_state_path
    runtime.availability_registry = (
        provider_availability_persistence_runtime_service.load_persisted_availability_registry(
            path=runtime.provider_availability_state_path
        )
    )
    runtime.provider_availability_registry = runtime.availability_registry
    runtime.run_manager = run_manager_cls()
    runtime.action_worker = action_worker or action_worker_cls()
    runtime.browser_action_executor = browser_action_executor
    runtime.gateway_state_store = gateway_state_store or gateway_state_store_cls()
    runtime.gateway_broadcaster = gateway_broadcaster or gateway_broadcaster_cls()
    runtime.runtime_policy = runtime_policy or runtime_policy_cls.normalized()
    runtime._current_dt_provider = current_dt_provider
    runtime.activity_callback = activity_callback
    runtime.turn_event_callback = turn_event_callback
    runtime.thread_workspace_context = None
    runtime._sync_agent_availability_registry()
    runtime.provider_availability_refresh_controller = (
        provider_availability_refresh_runtime_service.build_refresh_controller()
    )
    provider_availability_refresh_runtime_service.attach_refresh_controller(
        runtime,
        runtime.provider_availability_refresh_controller,
    )
    provider_availability_refresh_runtime_service.attach_refresh_controller(
        runtime.agent,
        runtime.provider_availability_refresh_controller,
    )
    runtime.cwd = runtime_runtime.bootstrap_runtime_environment(
        tools=runtime.tools,
        agent=runtime.agent,
        runtime_policy=runtime.runtime_policy,
        shell_activity_callback=runtime._emit_shell_activity,
        shell_activity_suppressed_getter=runtime._activity_callbacks_suppressed,
        shell_cancel_event_getter=runtime._active_cancel_event,
        resolve_runtime_cwd_fn=runtime._resolve_runtime_cwd,
        set_tools_workspace_root_fn=runtime._set_tools_workspace_root,
        runtime_policy_status_getter=runtime.runtime_policy_status,
        request_patch_approval_fn=runtime.request_patch_approval,
    )
    for attr_name, attr_value in runtime_runtime.runtime_init_state(
        threading_module=threading_module,
        thread_store=thread_store,
        run_command_text_result_fn=runtime._run_command_text_result,
        interrupt_requested_fn=runtime._is_interrupt_requested,
        interrupt_result_fn=runtime._interrupt_tuple,
        runtime_owner=runtime,
    ).items():
        setattr(runtime, attr_name, attr_value)
    runtime._rebuild_thread_workspace_context(thread_id=thread_id)
    if thread_store is not None and thread_id:
        runtime.resume_thread(thread_id)
    runtime._mcp_runtime = runtime._build_mcp_runtime()
    runtime._sync_request_user_input_mode_from_provider()


def bind_agent_cli_runtime_facade_methods(
    runtime_cls: Any,
    *,
    runtime_instance_methods_runtime_service: Any,
    run_thread_runtime_service: Any,
    runtime_core_facade_bindings_runtime_service: Any,
    runtime_delegated_bindings_runtime_service: Any,
    runtime_delegated_api_bindings_runtime_service: Any,
    runtime_policy_gateway_bindings_runtime_service: Any,
    runtime_shell_bindings_runtime_service: Any,
    runtime_prompt_context_bindings_runtime_service: Any,
    runtime_response_bindings_runtime_service: Any,
    runtime_projection_helpers_runtime_service: Any,
    taskbook_runtime_service: Any,
    cli_version: str,
    local_plan_disabled_note: str,
    local_approval_connector_key: str,
    local_approval_plugin_name: str,
    local_patch_approval_reason: str,
    local_shell_approval_reason: str,
    local_background_teammate_approval_reason: str,
    session_class: Any,
    now_iso_fn: Callable[[], str],
    preview_text_fn: Callable[..., Any],
    trace_fn: Callable[..., Any],
    build_background_task_adapter_proxy_fn: Callable[..., Any],
    background_task_adapter_builder_proxy_fn: Callable[..., Any],
    build_planner_proxy_fn: Callable[..., Any],
    find_github_workflow_run_proxy_fn: Callable[..., Any],
    current_host_platform_fn: Callable[..., Any],
    slash_command_specs_fn: Callable[..., Any],
    match_slash_commands_fn: Callable[..., Any],
    autocomplete_slash_command_fn: Callable[..., Any],
    github_action_artifact_refs_fn: Callable[..., Any],
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> None:
    runtime_instance_methods_runtime_service.bind_agent_cli_runtime_methods(runtime_cls)

    runtime_cls._emit_activity = run_thread_runtime_service.emit_activity
    runtime_cls._emit_turn_event = run_thread_runtime_service.emit_turn_event
    runtime_cls._normalized_turn_event_value = classmethod(
        run_thread_runtime_service.normalized_turn_event_value
    )
    runtime_cls._turn_event_replay_signature = classmethod(
        run_thread_runtime_service.turn_event_replay_signature
    )
    runtime_cls._activity_callbacks_suppressed = (
        run_thread_runtime_service.activity_callbacks_suppressed
    )
    runtime_cls._turn_event_callbacks_suppressed = (
        run_thread_runtime_service.turn_event_callbacks_suppressed
    )
    runtime_cls._active_cancel_event = run_thread_runtime_service.active_cancel_event
    runtime_cls._bound_cancel_event = run_thread_runtime_service.bound_cancel_event
    runtime_cls._bound_callback_suppression = (
        run_thread_runtime_service.bound_callback_suppression
    )
    runtime_cls.has_active_run = run_thread_runtime_service.has_active_run
    runtime_cls.pending_steer_supported = run_thread_runtime_service.pending_steer_supported
    runtime_cls.steer_active_run = run_thread_runtime_service.steer_active_run
    runtime_cls.take_pending_steer_input_items = (
        run_thread_runtime_service.take_pending_steer_input_items
    )
    runtime_cls.has_thread = run_thread_runtime_service.has_thread
    runtime_cls.start_thread = run_thread_runtime_service.start_thread
    runtime_cls.list_threads = run_thread_runtime_service.list_threads
    runtime_cls.resume_thread = run_thread_runtime_service.resume_thread
    runtime_cls.active_run_token = run_thread_runtime_service.active_run_token
    runtime_cls.interrupt_active_run = run_thread_runtime_service.interrupt_active_run
    runtime_cls._begin_run = run_thread_runtime_service.begin_run
    runtime_cls._finish_run = run_thread_runtime_service.finish_run
    runtime_cls._is_interrupt_requested = run_thread_runtime_service.is_interrupt_requested
    runtime_cls._interrupt_event = staticmethod(run_thread_runtime_service.interrupt_event)
    runtime_cls._interrupt_tuple = run_thread_runtime_service.interrupt_tuple
    runtime_cls._state_value = staticmethod(run_thread_runtime_service.runtime_state_value)
    runtime_cls._restore_provider_state = run_thread_runtime_service.restore_provider_state
    runtime_cls._emit_shell_activity = run_thread_runtime_service.emit_shell_activity
    runtime_cls._running_activity_for_tool = staticmethod(
        run_thread_runtime_service.running_activity_for_tool
    )
    runtime_cls._plan_activity_event = staticmethod(
        run_thread_runtime_service.plan_activity_event
    )
    runtime_cls._resolve_background_task_adapter_builder = staticmethod(
        background_task_adapter_builder_proxy_fn
    )

    runtime_core_facade_bindings_runtime_service.bind_runtime_core_facade_methods(
        runtime_cls,
        local_plan_disabled_note=local_plan_disabled_note,
    )
    runtime_delegated_bindings_runtime_service.bind_runtime_delegated_methods(
        runtime_cls,
        **runtime_projection_helpers_runtime_service.runtime_delegated_binding_kwargs(
            session_class=session_class,
            now_iso_fn=now_iso_fn,
            preview_text_fn=preview_text_fn,
            build_background_task_adapter_fn=build_background_task_adapter_proxy_fn,
            build_planner_fn=build_planner_proxy_fn,
            current_host_platform_fn=current_host_platform_fn,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
        ),
    )
    runtime_delegated_api_bindings_runtime_service.bind_runtime_delegated_api_methods(
        runtime_cls,
        **runtime_projection_helpers_runtime_service.runtime_delegated_api_binding_kwargs(
            session_class=session_class,
        ),
    )
    runtime_policy_gateway_bindings_runtime_service.bind_runtime_policy_gateway_methods(
        runtime_cls,
        **runtime_projection_helpers_runtime_service.runtime_policy_gateway_binding_kwargs(
            cli_version=cli_version,
            local_approval_connector_key=local_approval_connector_key,
            local_approval_plugin_name=local_approval_plugin_name,
            local_patch_approval_reason=local_patch_approval_reason,
            local_background_teammate_approval_reason=local_background_teammate_approval_reason,
            slash_command_specs_fn=slash_command_specs_fn,
            match_slash_commands_fn=match_slash_commands_fn,
            autocomplete_slash_command_fn=autocomplete_slash_command_fn,
            github_action_artifact_refs_fn=github_action_artifact_refs_fn,
            find_github_workflow_run_fn=find_github_workflow_run_proxy_fn,
        ),
    )
    runtime_shell_bindings_runtime_service.bind_runtime_shell_methods(
        runtime_cls,
        **runtime_projection_helpers_runtime_service.runtime_shell_binding_kwargs(
            trace_fn=trace_fn,
            preview_text_fn=preview_text_fn,
            connector_key=local_approval_connector_key,
            plugin_name=local_approval_plugin_name,
            approval_reason=local_shell_approval_reason,
        ),
    )
    runtime_prompt_context_bindings_runtime_service.bind_runtime_prompt_context_methods(
        runtime_cls
    )
    runtime_response_bindings_runtime_service.bind_runtime_response_methods(runtime_cls)

    runtime_cls._orchestration_runtime_services = taskbook_runtime_service.runtime_services
    runtime_cls.preview_orchestration_run = taskbook_runtime_service.preview_orchestration_run
    runtime_cls.create_orchestration_run = taskbook_runtime_service.create_orchestration_run
    runtime_cls.dispatch_orchestration_run = taskbook_runtime_service.dispatch_orchestration_run
    runtime_cls.progress_orchestration_run = taskbook_runtime_service.progress_orchestration_run
    runtime_cls.continue_orchestration_run = taskbook_runtime_service.continue_orchestration_run
    runtime_cls.apply_orchestration_card = taskbook_runtime_service.apply_orchestration_card
    runtime_cls.reject_orchestration_card = taskbook_runtime_service.reject_orchestration_card
    runtime_cls.list_orchestration_workflows = (
        taskbook_runtime_service.list_orchestration_workflows
    )


__all__ = [
    "bind_agent_cli_runtime_facade_methods",
    "build_runtime_background_task_adapter_builder_proxy",
    "build_runtime_background_task_adapter_proxy",
    "build_runtime_build_planner_proxy",
    "build_runtime_find_github_workflow_run_proxy",
    "initialize_agent_cli_runtime",
]
