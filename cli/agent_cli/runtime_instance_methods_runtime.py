from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli import runtime_context_runtime as runtime_context_runtime_service
from cli.agent_cli import runtime_helpers_runtime as runtime_helpers_runtime_service
from cli.agent_cli import runtime_runtime
from cli.agent_cli import runtime_runtime_state_runtime as runtime_state_runtime_service
from cli.agent_cli.mcp import McpRuntimeFacade
from cli.agent_cli.models import ToolEvent


@dataclass
class _DelegatedAgentSession:
    agent_id: str
    role: str
    config: Any
    timeout: int | None
    source: str
    protocol_run_id: str = ""
    protocol_parent_run_id: str = ""
    protocol_thread_id: str = ""
    resume_source: str = "spawn_agent"
    delegation_reason: str = ""
    delegation_mode: str = ""
    wait_required: bool | None = None
    task_shape: str = ""
    subagent_type: str = ""
    background_priority: str = ""
    parallel_group: str = ""
    scheduler_reason: str = ""
    seed_input_items: list[dict[str, Any]] = field(default_factory=list)
    seed_history: list[dict[str, str]] = field(default_factory=list)
    replay_input_items: list[dict[str, Any]] = field(default_factory=list)
    replay_history: list[dict[str, str]] = field(default_factory=list)
    progress_steps: list[dict[str, Any]] = field(default_factory=list)
    progress_checkpoints: list[dict[str, Any]] = field(default_factory=list)
    current_step_id: str = ""
    queued_inputs: list[dict[str, Any]] = field(default_factory=list)
    active_input: dict[str, Any] | None = None
    created_at: str = field(default_factory=runtime_helpers_runtime_service.runtime_now_iso)
    updated_at: str = field(default_factory=runtime_helpers_runtime_service.runtime_now_iso)
    status: str = "queued"
    last_input_text: str = ""
    assistant_text: str = ""
    error: str = ""
    last_tool_events: list[ToolEvent] = field(default_factory=list)
    last_item_events: list[dict[str, Any]] = field(default_factory=list)
    last_turn_events: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    adopted: bool = False
    adopted_at: str = ""
    last_wait_reason: str = ""
    last_wait_decision: str = ""
    last_wait_at: str = ""
    last_wait_blocked_ms: int | None = None
    last_wait_timed_out: bool = False
    terminal_reason: str = ""
    close_requested: bool = False
    closed: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    worker: threading.Thread | None = None
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)


def _sync_request_user_input_mode_from_provider(self: Any) -> bool:
    return runtime_helpers_runtime_service.sync_runtime_request_user_input_mode(self)


def _build_mcp_runtime(self: Any) -> McpRuntimeFacade:
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: getattr(self.tools, "_plugin_manager", None),
        runtime_policy_getter=lambda: self.runtime_policy,
    )
    setter = getattr(self.tools, "set_mcp_runtime", None)
    if callable(setter):
        setter(runtime)
    else:
        self.tools._mcp_runtime = runtime
    plugin_manager = getattr(self.tools, "_plugin_manager", None)
    if plugin_manager is not None:
        plugin_manager._mcp_runtime = runtime
        plugin_manager.mcp_provider_tool_specs = runtime.provider_tool_specs
        plugin_manager.mcp_tool_specs = runtime.tool_specs
        plugin_manager.mcp_command_specs = runtime.command_specs
        plugin_manager.mcp_execute_command = runtime.execute_command
        plugin_manager.mcp_server_entries = runtime.server_entries
        plugin_manager.mcp_server_runtime_map = runtime.capability_mcp_servers
    return runtime


def get_mcp_runtime(self: Any) -> McpRuntimeFacade | None:
    return getattr(self, "_mcp_runtime", None)


def _sync_agent_availability_registry(self: Any) -> None:
    setter = getattr(self.agent, "set_availability_registry", None)
    if callable(setter):
        setter(self.availability_registry)
    else:
        self.agent._provider_availability_registry = self.availability_registry
    state_path = getattr(self, "provider_availability_state_path", None)
    if state_path is None:
        state_path = getattr(self, "_provider_availability_state_path", None)
    self.agent._provider_availability_state_path = state_path
    self.agent.provider_availability_state_path = state_path


def _rebuild_thread_workspace_context(self: Any, *, thread_id: str | None = None) -> None:
    workspace_root = str(
        runtime_context_runtime_service.tools_file_workspace_root(tools=self.tools)
    )
    self.thread_workspace_context = runtime_state_runtime_service.runtime_workspace_context_state(
        thread_id=thread_id if thread_id is not None else getattr(self, "thread_id", None),
        cwd=self.cwd,
        runtime_policy=self.runtime_policy,
        workspace_root=workspace_root,
        build_runtime_workspace_context_fn=runtime_context_runtime_service.build_runtime_workspace_context,
    )


def _refresh_thread_workspace_context_after_cwd_change(self: Any) -> None:
    workspace_root = str(
        runtime_context_runtime_service.tools_file_workspace_root(tools=self.tools)
    )
    updated = runtime_state_runtime_service.runtime_workspace_context_after_cwd_change(
        self.thread_workspace_context,
        cwd=self.cwd,
        workspace_root=workspace_root,
        refresh_workspace_context_for_cwd_fn=runtime_context_runtime_service.refresh_workspace_context_for_cwd,
    )
    if updated is None:
        self._rebuild_thread_workspace_context()
        return
    self.thread_workspace_context = updated


def _refresh_thread_workspace_context_after_policy_change(self: Any) -> None:
    updated = runtime_state_runtime_service.runtime_workspace_context_after_policy_change(
        self.thread_workspace_context,
        runtime_policy=self.runtime_policy,
        refresh_workspace_context_for_runtime_policy_fn=runtime_context_runtime_service.refresh_workspace_context_for_runtime_policy,
    )
    if updated is None:
        self._rebuild_thread_workspace_context()
        return
    self.thread_workspace_context = updated


def _resolve_runtime_cwd(value: Any | None) -> Path:
    return runtime_runtime.resolve_runtime_cwd(value)


def _set_tools_workspace_root(self: Any, path: Path) -> Path:
    return runtime_runtime.set_tools_workspace_root(tools=self.tools, path=path)


def set_cwd(self: Any, cwd: str | Path) -> Path:
    self.cwd, cache_state = runtime_runtime.runtime_cwd_state(
        cwd=cwd,
        resolve_runtime_cwd_fn=self._resolve_runtime_cwd,
        set_tools_workspace_root_fn=self._set_tools_workspace_root,
        agent_setter=getattr(self.agent, "set_cwd", None),
    )
    for attr_name, attr_value in cache_state.items():
        setattr(self, attr_name, attr_value)
    self._refresh_thread_workspace_context_after_cwd_change()
    return self.cwd


def set_context_snapshot_overrides(
    self: Any,
    *,
    environment_snapshot: dict[str, Any] | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
) -> None:
    (
        self._forced_environment_context_snapshot,
        self._forced_workspace_context_snapshot,
    ) = runtime_runtime.context_snapshot_overrides(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
    )


def configure_model_selection(
    self: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    persist: bool = False,
    write_scope: str | None = None,
) -> dict[str, str]:
    status = dict(
        runtime_runtime.configure_model_selection(
            agent=self.agent,
            model=model,
            reasoning_effort=reasoning_effort,
            persist=persist,
            write_scope=write_scope,
        )
    )
    self._sync_request_user_input_mode_from_provider()
    return status


def configure_route_selection(
    self: Any,
    route_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
) -> dict[str, str]:
    status = dict(
        runtime_runtime.configure_named_selection(
            agent=self.agent,
            configurator_name="configure_route_selection",
            disabled_error="route override switch disabled",
            target_name=route_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )
    )
    self._sync_request_user_input_mode_from_provider()
    return status


def configure_delegate_selection(
    self: Any,
    role_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
) -> dict[str, str]:
    status = dict(
        runtime_runtime.configure_delegate_selection(
            agent=self.agent,
            role_name=role_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
            cleanup_delegated_sessions_for_role_fn=lambda value: self._cleanup_delegated_sessions_for_role(
                value,
                reason="role_override_changed",
            ),
        )
    )
    self._sync_request_user_input_mode_from_provider()
    return status


def bind_agent_cli_runtime_methods(runtime_cls: Any) -> None:
    runtime_cls._sync_request_user_input_mode_from_provider = (
        _sync_request_user_input_mode_from_provider
    )
    runtime_cls._build_mcp_runtime = _build_mcp_runtime
    runtime_cls.get_mcp_runtime = get_mcp_runtime
    runtime_cls._sync_agent_availability_registry = _sync_agent_availability_registry
    runtime_cls._rebuild_thread_workspace_context = _rebuild_thread_workspace_context
    runtime_cls._refresh_thread_workspace_context_after_cwd_change = (
        _refresh_thread_workspace_context_after_cwd_change
    )
    runtime_cls._refresh_thread_workspace_context_after_policy_change = (
        _refresh_thread_workspace_context_after_policy_change
    )
    runtime_cls._resolve_runtime_cwd = staticmethod(_resolve_runtime_cwd)
    runtime_cls._set_tools_workspace_root = _set_tools_workspace_root
    runtime_cls.set_cwd = set_cwd
    runtime_cls.set_context_snapshot_overrides = set_context_snapshot_overrides
    runtime_cls.configure_model_selection = configure_model_selection
    runtime_cls.configure_route_selection = configure_route_selection
    runtime_cls.configure_delegate_selection = configure_delegate_selection
