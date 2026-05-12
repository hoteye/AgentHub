from __future__ import annotations

from typing import Any, Callable


def build_planner_proxy(
    *args: Any,
    build_planner_fn: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    return build_planner_fn(*args, **kwargs)


def background_task_adapter_builder_proxy(
    *,
    build_background_task_adapter_fn: Callable[..., Any],
) -> Callable[..., Any]:
    return build_background_task_adapter_fn


def build_background_task_adapter_proxy(
    *args: Any,
    build_background_task_adapter_fn: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    return build_background_task_adapter_fn(*args, **kwargs)


def find_github_workflow_run_proxy(
    *args: Any,
    find_github_workflow_run_fn: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    return find_github_workflow_run_fn(*args, **kwargs)


def restore_provider_state_with_request_user_input_sync(
    self: Any,
    state: dict[str, Any],
    *,
    original_restore_provider_state_fn: Callable[[Any, dict[str, Any]], None],
) -> None:
    original_restore_provider_state_fn(self, state)
    self._sync_request_user_input_mode_from_provider()


def start_thread_with_workspace_context_sync(
    self: Any,
    *,
    name: str | None = None,
    cwd: str | None = None,
    original_start_thread_fn: Callable[..., Any],
    start_thread_payload_thread_id_fn: Callable[[Any], str | None],
) -> Any:
    payload = original_start_thread_fn(self, name=name, cwd=cwd)
    self._rebuild_thread_workspace_context(thread_id=start_thread_payload_thread_id_fn(payload))
    return payload


def resume_thread_with_workspace_context_sync(
    self: Any,
    thread_id: str | None = None,
    *,
    path: str | None = None,
    history: list[dict[str, Any]] | None = None,
    original_resume_thread_fn: Callable[..., Any],
    resume_thread_workspace_context_fn: Callable[..., Any],
) -> Any:
    payload = original_resume_thread_fn(self, thread_id, path=path, history=history)
    self.thread_workspace_context = resume_thread_workspace_context_fn(
        tools=self.tools,
        thread_workspace_context=self.thread_workspace_context,
        thread_id=getattr(self, "thread_id", None),
        cwd=self.cwd,
        runtime_policy=self.runtime_policy,
    )
    return payload


def configure_runtime_policy_with_workspace_context_sync(
    self: Any,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    web_search_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
    original_configure_runtime_policy_fn: Callable[..., Any],
) -> Any:
    status = original_configure_runtime_policy_fn(
        self,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
    )
    self._refresh_thread_workspace_context_after_policy_change()
    return status


def handle_prompt_with_request_user_input_sync(
    self: Any,
    text: str,
    *,
    attachments: list[Any] | None = None,
    original_handle_prompt_fn: Callable[..., Any],
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
    maybe_reload_planner_for_provider_gate_update_fn: Callable[..., Any],
) -> Any:
    self._sync_request_user_input_mode_from_provider()
    schedule_stale_on_use_refresh_fn(self, reason="prompt_use")
    maybe_reload_planner_for_provider_gate_update_fn(self.agent)
    response = original_handle_prompt_fn(self, text, attachments=attachments)
    maybe_reload_planner_for_provider_gate_update_fn(self.agent)
    return response


def run_command_text_result_with_request_user_input_sync(
    self: Any,
    text: str,
    *,
    original_run_command_text_result_fn: Callable[[Any, str], Any],
) -> Any:
    self._sync_request_user_input_mode_from_provider()
    return original_run_command_text_result_fn(self, text)


def configure_model_selection_with_provider_availability_refresh(
    self: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    persist: bool = False,
    write_scope: str | None = None,
    original_configure_model_selection_fn: Callable[..., Any],
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Any:
    status = original_configure_model_selection_fn(
        self,
        model=model,
        reasoning_effort=reasoning_effort,
        persist=persist,
        write_scope=write_scope,
    )
    schedule_stale_on_use_refresh_fn(self, reason="model_selection_change")
    return status


def configure_route_selection_with_provider_availability_refresh(
    self: Any,
    route_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
    original_configure_route_selection_fn: Callable[..., Any],
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Any:
    status = original_configure_route_selection_fn(
        self,
        route_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
    )
    schedule_stale_on_use_refresh_fn(self, reason="route_selection_change")
    return status


def configure_delegate_selection_with_provider_availability_refresh(
    self: Any,
    role_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
    original_configure_delegate_selection_fn: Callable[..., Any],
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Any:
    status = original_configure_delegate_selection_fn(
        self,
        role_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
    )
    schedule_stale_on_use_refresh_fn(self, reason="delegate_selection_change")
    return status


__all__ = [
    "background_task_adapter_builder_proxy",
    "build_background_task_adapter_proxy",
    "build_planner_proxy",
    "configure_delegate_selection_with_provider_availability_refresh",
    "configure_model_selection_with_provider_availability_refresh",
    "configure_route_selection_with_provider_availability_refresh",
    "configure_runtime_policy_with_workspace_context_sync",
    "find_github_workflow_run_proxy",
    "handle_prompt_with_request_user_input_sync",
    "restore_provider_state_with_request_user_input_sync",
    "resume_thread_with_workspace_context_sync",
    "run_command_text_result_with_request_user_input_sync",
    "start_thread_with_workspace_context_sync",
]
