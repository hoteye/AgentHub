from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cli.agent_cli import __version__, runtime_runtime
from cli.agent_cli import (
    runtime_core_facade_bindings_runtime as runtime_core_facade_bindings_runtime_service,
)
from cli.agent_cli import (
    runtime_delegated_api_bindings_runtime as runtime_delegated_api_bindings_runtime_service,
)
from cli.agent_cli import (
    runtime_delegated_bindings_runtime as runtime_delegated_bindings_runtime_service,
)
from cli.agent_cli import runtime_facade_bindings_runtime as runtime_facade_bindings_runtime_service
from cli.agent_cli import (
    runtime_facade_sync_overrides_runtime as runtime_facade_sync_overrides_runtime_service,
)
from cli.agent_cli import runtime_helpers_runtime as runtime_helpers_runtime_service
from cli.agent_cli import (
    runtime_instance_methods_runtime as runtime_instance_methods_runtime_service,
)
from cli.agent_cli import (
    runtime_normalization_helpers_runtime as runtime_normalization_helpers_runtime_service,
)
from cli.agent_cli import (
    runtime_policy_gateway_bindings_runtime as runtime_policy_gateway_bindings_runtime_service,
)
from cli.agent_cli import (
    runtime_projection_helpers_runtime as runtime_projection_helpers_runtime_service,
)
from cli.agent_cli import (
    runtime_prompt_context_bindings_runtime as runtime_prompt_context_bindings_runtime_service,
)
from cli.agent_cli import runtime_pure_helpers_runtime as runtime_pure_helpers_runtime_service
from cli.agent_cli import (
    runtime_response_bindings_runtime as runtime_response_bindings_runtime_service,
)
from cli.agent_cli import runtime_shell_bindings_runtime as runtime_shell_bindings_runtime_service
from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.gateway_core import InMemoryGatewayStateStore
from cli.agent_cli.gateway_server.event_broadcast import GatewayEventBroadcaster
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.provider import build_planner as _provider_build_planner
from cli.agent_cli.providers import (
    availability_persistence_runtime as provider_availability_persistence_runtime_service,
)
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.runtime_runs import RunManager
from cli.agent_cli.runtime_services import (
    provider_availability_refresh_runtime as provider_availability_refresh_runtime_service,
)
from cli.agent_cli.runtime_services import run_thread_runtime as run_thread_runtime_service
from cli.agent_cli.slash_commands import (
    autocomplete_slash_command,
    match_slash_commands,
    slash_command_specs,
)
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.tools import ToolRegistry
from shared.integrations import find_github_workflow_run, github_action_artifact_refs
from workers.actions import ActionResult, ControlledActionWorker

_LOCAL_PLAN_DISABLED_NOTE = "Built-in local automation planning has been disabled."
_LOCAL_APPROVAL_CONNECTOR_KEY = "local_cli"
_LOCAL_APPROVAL_PLUGIN_NAME = "local_cli"
_LOCAL_PATCH_APPROVAL_REASON = (
    "Structured workspace patches require manual approval before file changes are applied."
)
_LOCAL_SHELL_APPROVAL_REASON = (
    "Shell command execution requires manual approval under the current runtime policy."
)
_LOCAL_BACKGROUND_TEAMMATE_APPROVAL_REASON = "Background teammate live-workspace execution requires manual approval before the task is queued."
_DELEGATED_MAX_ACTIVE = 4
_DELEGATED_READ_ONLY_MAX_ACTIVE = 3
_DELEGATED_LONG_RUNNING_MAX_ACTIVE = 2
_DELEGATED_SERIAL_TASK_SHAPES = frozenset({"workspace_mutating", "context_sensitive"})


_preview_text = runtime_helpers_runtime_service.preview_text
_tool_runtime_trace = runtime_helpers_runtime_service.tool_runtime_trace
_runtime_now_iso = runtime_helpers_runtime_service.runtime_now_iso
runtime_request_user_input_default_mode_enabled = (
    runtime_helpers_runtime_service.runtime_request_user_input_default_mode_enabled
)
sync_runtime_request_user_input_mode = (
    runtime_helpers_runtime_service.sync_runtime_request_user_input_mode
)
_DelegatedAgentSession = runtime_instance_methods_runtime_service._DelegatedAgentSession


def build_planner(*args: Any, **kwargs: Any) -> Any:
    return _provider_build_planner(*args, **kwargs)


def build_background_task_adapter(*args: Any, **kwargs: Any) -> Any:
    return runtime_helpers_runtime_service.runtime_build_background_task_adapter(*args, **kwargs)


_runtime_build_planner_proxy = (
    runtime_facade_bindings_runtime_service.build_runtime_build_planner_proxy(
        get_build_planner_fn=lambda: build_planner,
        runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    )
)
_runtime_background_task_adapter_builder_proxy = (
    runtime_facade_bindings_runtime_service.build_runtime_background_task_adapter_builder_proxy(
        get_build_background_task_adapter_fn=lambda: build_background_task_adapter,
        runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    )
)
_runtime_build_background_task_adapter_proxy = (
    runtime_facade_bindings_runtime_service.build_runtime_background_task_adapter_proxy(
        get_build_background_task_adapter_fn=lambda: build_background_task_adapter,
        runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    )
)
_runtime_find_github_workflow_run_proxy = runtime_facade_bindings_runtime_service.build_runtime_find_github_workflow_run_proxy(
    # Resolve from runtime module globals at call-time so tests can patch this symbol.
    get_find_github_workflow_run_fn=lambda: find_github_workflow_run,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
)


class AgentCliRuntime:
    _PLANNER_HISTORY_LIMIT_MESSAGES = 24
    _AUTO_COMPACT_TRIGGER_ITEMS = 24
    _AUTO_COMPACT_TRIGGER_TOKENS = 0
    _AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT = 90
    _MODEL_COMPACT_SOURCE_MAX_CHARS = 12_000

    def __init__(
        self,
        *,
        tools: ToolRegistry | None = None,
        agent: RuleBasedAgent | None = None,
        activity_callback: Callable[[ActivityEvent], None] | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
        thread_store: ThreadStore | None = None,
        thread_id: str | None = None,
        gateway_state_store: InMemoryGatewayStateStore | None = None,
        action_worker: ControlledActionWorker | None = None,
        browser_action_executor: Callable[[Any], ActionResult | dict[str, Any]] | None = None,
        runtime_policy: RuntimePolicy | None = None,
        gateway_broadcaster: GatewayEventBroadcaster | None = None,
        current_dt_provider: Callable[[], datetime] | None = None,
    ) -> None:
        runtime_facade_bindings_runtime_service.initialize_agent_cli_runtime(
            self,
            tools=tools,
            agent=agent,
            activity_callback=activity_callback,
            turn_event_callback=turn_event_callback,
            thread_store=thread_store,
            thread_id=thread_id,
            gateway_state_store=gateway_state_store,
            action_worker=action_worker,
            browser_action_executor=browser_action_executor,
            runtime_policy=runtime_policy,
            gateway_broadcaster=gateway_broadcaster,
            current_dt_provider=current_dt_provider,
            tool_registry_cls=ToolRegistry,
            agent_cls=RuleBasedAgent,
            provider_availability_persistence_runtime_service=provider_availability_persistence_runtime_service,
            run_manager_cls=RunManager,
            action_worker_cls=ControlledActionWorker,
            gateway_state_store_cls=InMemoryGatewayStateStore,
            gateway_broadcaster_cls=GatewayEventBroadcaster,
            runtime_policy_cls=RuntimePolicy,
            provider_availability_refresh_runtime_service=provider_availability_refresh_runtime_service,
            runtime_runtime=runtime_runtime,
            threading_module=threading,
        )


runtime_facade_bindings_runtime_service.bind_agent_cli_runtime_facade_methods(
    AgentCliRuntime,
    runtime_instance_methods_runtime_service=runtime_instance_methods_runtime_service,
    run_thread_runtime_service=run_thread_runtime_service,
    runtime_core_facade_bindings_runtime_service=runtime_core_facade_bindings_runtime_service,
    runtime_delegated_bindings_runtime_service=runtime_delegated_bindings_runtime_service,
    runtime_delegated_api_bindings_runtime_service=runtime_delegated_api_bindings_runtime_service,
    runtime_policy_gateway_bindings_runtime_service=runtime_policy_gateway_bindings_runtime_service,
    runtime_shell_bindings_runtime_service=runtime_shell_bindings_runtime_service,
    runtime_prompt_context_bindings_runtime_service=runtime_prompt_context_bindings_runtime_service,
    runtime_response_bindings_runtime_service=runtime_response_bindings_runtime_service,
    runtime_projection_helpers_runtime_service=runtime_projection_helpers_runtime_service,
    taskbook_runtime_service=taskbook_runtime_service,
    cli_version=__version__,
    local_plan_disabled_note=_LOCAL_PLAN_DISABLED_NOTE,
    local_approval_connector_key=_LOCAL_APPROVAL_CONNECTOR_KEY,
    local_approval_plugin_name=_LOCAL_APPROVAL_PLUGIN_NAME,
    local_patch_approval_reason=_LOCAL_PATCH_APPROVAL_REASON,
    local_shell_approval_reason=_LOCAL_SHELL_APPROVAL_REASON,
    local_background_teammate_approval_reason=_LOCAL_BACKGROUND_TEAMMATE_APPROVAL_REASON,
    session_class=_DelegatedAgentSession,
    now_iso_fn=_runtime_now_iso,
    preview_text_fn=_preview_text,
    trace_fn=_tool_runtime_trace,
    build_background_task_adapter_proxy_fn=_runtime_build_background_task_adapter_proxy,
    background_task_adapter_builder_proxy_fn=_runtime_background_task_adapter_builder_proxy,
    build_planner_proxy_fn=_runtime_build_planner_proxy,
    find_github_workflow_run_proxy_fn=_runtime_find_github_workflow_run_proxy,
    current_host_platform_fn=current_host_platform,
    slash_command_specs_fn=slash_command_specs,
    match_slash_commands_fn=match_slash_commands,
    autocomplete_slash_command_fn=autocomplete_slash_command,
    github_action_artifact_refs_fn=github_action_artifact_refs,
    max_active=_DELEGATED_MAX_ACTIVE,
    read_only_max_active=_DELEGATED_READ_ONLY_MAX_ACTIVE,
    long_running_max_active=_DELEGATED_LONG_RUNNING_MAX_ACTIVE,
)

_captured_override_methods = (
    runtime_facade_sync_overrides_runtime_service.capture_original_runtime_override_methods(
        AgentCliRuntime
    )
)
_ORIGINAL_RESTORE_PROVIDER_STATE = _captured_override_methods["restore_provider_state"]
_ORIGINAL_START_THREAD = _captured_override_methods["start_thread"]
_ORIGINAL_RESUME_THREAD = _captured_override_methods["resume_thread"]
_ORIGINAL_CONFIGURE_RUNTIME_POLICY = _captured_override_methods["configure_runtime_policy"]
_ORIGINAL_HANDLE_PROMPT = _captured_override_methods["handle_prompt"]
_ORIGINAL_RUN_COMMAND_TEXT_RESULT = _captured_override_methods["run_command_text_result"]
_ORIGINAL_CONFIGURE_MODEL_SELECTION = _captured_override_methods["configure_model_selection"]
_ORIGINAL_CONFIGURE_ROUTE_SELECTION = _captured_override_methods["configure_route_selection"]
_ORIGINAL_CONFIGURE_DELEGATE_SELECTION = _captured_override_methods["configure_delegate_selection"]

_restore_provider_state_with_request_user_input_sync = runtime_facade_sync_overrides_runtime_service.build_restore_provider_state_with_request_user_input_sync(
    get_original_restore_provider_state_fn=lambda: _ORIGINAL_RESTORE_PROVIDER_STATE,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
)
_start_thread_with_workspace_context_sync = runtime_facade_sync_overrides_runtime_service.build_start_thread_with_workspace_context_sync(
    get_original_start_thread_fn=lambda: _ORIGINAL_START_THREAD,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    start_thread_payload_thread_id_fn=runtime_normalization_helpers_runtime_service.start_thread_payload_thread_id,
)
_resume_thread_with_workspace_context_sync = runtime_facade_sync_overrides_runtime_service.build_resume_thread_with_workspace_context_sync(
    get_original_resume_thread_fn=lambda: _ORIGINAL_RESUME_THREAD,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    resume_thread_workspace_context_fn=runtime_projection_helpers_runtime_service.resume_thread_workspace_context,
)
_configure_runtime_policy_with_workspace_context_sync = runtime_facade_sync_overrides_runtime_service.build_configure_runtime_policy_with_workspace_context_sync(
    get_original_configure_runtime_policy_fn=lambda: _ORIGINAL_CONFIGURE_RUNTIME_POLICY,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
)
_handle_prompt_with_request_user_input_sync = runtime_facade_sync_overrides_runtime_service.build_handle_prompt_with_request_user_input_sync(
    get_original_handle_prompt_fn=lambda: _ORIGINAL_HANDLE_PROMPT,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    schedule_stale_on_use_refresh_fn=provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh,
    maybe_reload_planner_for_provider_gate_update_fn=provider_availability_refresh_runtime_service.maybe_reload_planner_for_provider_gate_update,
)
_run_command_text_result_with_request_user_input_sync = runtime_facade_sync_overrides_runtime_service.build_run_command_text_result_with_request_user_input_sync(
    get_original_run_command_text_result_fn=lambda: _ORIGINAL_RUN_COMMAND_TEXT_RESULT,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
)
_configure_model_selection_with_provider_availability_refresh = runtime_facade_sync_overrides_runtime_service.build_configure_model_selection_with_provider_availability_refresh(
    get_original_configure_model_selection_fn=lambda: _ORIGINAL_CONFIGURE_MODEL_SELECTION,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    schedule_stale_on_use_refresh_fn=provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh,
)
_configure_route_selection_with_provider_availability_refresh = runtime_facade_sync_overrides_runtime_service.build_configure_route_selection_with_provider_availability_refresh(
    get_original_configure_route_selection_fn=lambda: _ORIGINAL_CONFIGURE_ROUTE_SELECTION,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    schedule_stale_on_use_refresh_fn=provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh,
)
_configure_delegate_selection_with_provider_availability_refresh = runtime_facade_sync_overrides_runtime_service.build_configure_delegate_selection_with_provider_availability_refresh(
    get_original_configure_delegate_selection_fn=lambda: _ORIGINAL_CONFIGURE_DELEGATE_SELECTION,
    runtime_pure_helpers_runtime_service=runtime_pure_helpers_runtime_service,
    schedule_stale_on_use_refresh_fn=provider_availability_refresh_runtime_service.schedule_stale_on_use_refresh,
)

runtime_facade_sync_overrides_runtime_service.bind_runtime_override_methods(
    AgentCliRuntime,
    restore_provider_state_fn=_restore_provider_state_with_request_user_input_sync,
    start_thread_fn=_start_thread_with_workspace_context_sync,
    resume_thread_fn=_resume_thread_with_workspace_context_sync,
    configure_runtime_policy_fn=_configure_runtime_policy_with_workspace_context_sync,
    handle_prompt_fn=_handle_prompt_with_request_user_input_sync,
    run_command_text_result_fn=_run_command_text_result_with_request_user_input_sync,
    configure_model_selection_fn=_configure_model_selection_with_provider_availability_refresh,
    configure_route_selection_fn=_configure_route_selection_with_provider_availability_refresh,
    configure_delegate_selection_fn=_configure_delegate_selection_with_provider_availability_refresh,
)
