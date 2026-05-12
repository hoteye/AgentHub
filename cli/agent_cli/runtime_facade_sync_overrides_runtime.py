from __future__ import annotations

from typing import Any, Callable


def capture_original_runtime_override_methods(runtime_cls: Any) -> dict[str, Any]:
    return {
        "restore_provider_state": runtime_cls._restore_provider_state,
        "start_thread": runtime_cls.start_thread,
        "resume_thread": runtime_cls.resume_thread,
        "configure_runtime_policy": runtime_cls.configure_runtime_policy,
        "handle_prompt": runtime_cls.handle_prompt,
        "run_command_text_result": runtime_cls._run_command_text_result,
        "configure_model_selection": runtime_cls.configure_model_selection,
        "configure_route_selection": runtime_cls.configure_route_selection,
        "configure_delegate_selection": runtime_cls.configure_delegate_selection,
    }


def build_restore_provider_state_with_request_user_input_sync(
    *,
    get_original_restore_provider_state_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., None]:
    def _restore_provider_state_with_request_user_input_sync(
        self: Any,
        state: dict[str, Any],
    ) -> None:
        runtime_pure_helpers_runtime_service.restore_provider_state_with_request_user_input_sync(
            self,
            state,
            original_restore_provider_state_fn=get_original_restore_provider_state_fn(),
        )

    return _restore_provider_state_with_request_user_input_sync


def build_start_thread_with_workspace_context_sync(
    *,
    get_original_start_thread_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    start_thread_payload_thread_id_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _start_thread_with_workspace_context_sync(
        self: Any,
        *,
        name: str | None = None,
        cwd: str | None = None,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.start_thread_with_workspace_context_sync(
            self,
            name=name,
            cwd=cwd,
            original_start_thread_fn=get_original_start_thread_fn(),
            start_thread_payload_thread_id_fn=start_thread_payload_thread_id_fn,
        )

    return _start_thread_with_workspace_context_sync


def build_resume_thread_with_workspace_context_sync(
    *,
    get_original_resume_thread_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    resume_thread_workspace_context_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _resume_thread_with_workspace_context_sync(
        self: Any,
        thread_id: str | None = None,
        *,
        path: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.resume_thread_with_workspace_context_sync(
            self,
            thread_id,
            path=path,
            history=history,
            original_resume_thread_fn=get_original_resume_thread_fn(),
            resume_thread_workspace_context_fn=resume_thread_workspace_context_fn,
        )

    return _resume_thread_with_workspace_context_sync


def build_configure_runtime_policy_with_workspace_context_sync(
    *,
    get_original_configure_runtime_policy_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., Any]:
    def _configure_runtime_policy_with_workspace_context_sync(
        self: Any,
        *,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
        web_search_mode: str | None = None,
        network_access_enabled: str | bool | None = None,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.configure_runtime_policy_with_workspace_context_sync(
            self,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            web_search_mode=web_search_mode,
            network_access_enabled=network_access_enabled,
            original_configure_runtime_policy_fn=get_original_configure_runtime_policy_fn(),
        )

    return _configure_runtime_policy_with_workspace_context_sync


def build_handle_prompt_with_request_user_input_sync(
    *,
    get_original_handle_prompt_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
    maybe_reload_planner_for_provider_gate_update_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _handle_prompt_with_request_user_input_sync(
        self: Any,
        text: str,
        *,
        attachments: list[Any] | None = None,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.handle_prompt_with_request_user_input_sync(
            self,
            text,
            attachments=attachments,
            original_handle_prompt_fn=get_original_handle_prompt_fn(),
            schedule_stale_on_use_refresh_fn=schedule_stale_on_use_refresh_fn,
            maybe_reload_planner_for_provider_gate_update_fn=(
                maybe_reload_planner_for_provider_gate_update_fn
            ),
        )

    return _handle_prompt_with_request_user_input_sync


def build_run_command_text_result_with_request_user_input_sync(
    *,
    get_original_run_command_text_result_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
) -> Callable[..., Any]:
    def _run_command_text_result_with_request_user_input_sync(
        self: Any,
        text: str,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.run_command_text_result_with_request_user_input_sync(
            self,
            text,
            original_run_command_text_result_fn=get_original_run_command_text_result_fn(),
        )

    return _run_command_text_result_with_request_user_input_sync


def build_configure_model_selection_with_provider_availability_refresh(
    *,
    get_original_configure_model_selection_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _configure_model_selection_with_provider_availability_refresh(
        self: Any,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        persist: bool = False,
        write_scope: str | None = None,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.configure_model_selection_with_provider_availability_refresh(
            self,
            model=model,
            reasoning_effort=reasoning_effort,
            persist=persist,
            write_scope=write_scope,
            original_configure_model_selection_fn=get_original_configure_model_selection_fn(),
            schedule_stale_on_use_refresh_fn=schedule_stale_on_use_refresh_fn,
        )

    return _configure_model_selection_with_provider_availability_refresh


def build_configure_route_selection_with_provider_availability_refresh(
    *,
    get_original_configure_route_selection_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _configure_route_selection_with_provider_availability_refresh(
        self: Any,
        route_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
        clear: bool = False,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.configure_route_selection_with_provider_availability_refresh(
            self,
            route_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
            original_configure_route_selection_fn=get_original_configure_route_selection_fn(),
            schedule_stale_on_use_refresh_fn=schedule_stale_on_use_refresh_fn,
        )

    return _configure_route_selection_with_provider_availability_refresh


def build_configure_delegate_selection_with_provider_availability_refresh(
    *,
    get_original_configure_delegate_selection_fn: Callable[[], Callable[..., Any]],
    runtime_pure_helpers_runtime_service: Any,
    schedule_stale_on_use_refresh_fn: Callable[..., Any],
) -> Callable[..., Any]:
    def _configure_delegate_selection_with_provider_availability_refresh(
        self: Any,
        role_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
        clear: bool = False,
    ) -> Any:
        return runtime_pure_helpers_runtime_service.configure_delegate_selection_with_provider_availability_refresh(
            self,
            role_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
            original_configure_delegate_selection_fn=get_original_configure_delegate_selection_fn(),
            schedule_stale_on_use_refresh_fn=schedule_stale_on_use_refresh_fn,
        )

    return _configure_delegate_selection_with_provider_availability_refresh


def bind_runtime_override_methods(
    runtime_cls: Any,
    *,
    restore_provider_state_fn: Callable[..., Any],
    start_thread_fn: Callable[..., Any],
    resume_thread_fn: Callable[..., Any],
    configure_runtime_policy_fn: Callable[..., Any],
    handle_prompt_fn: Callable[..., Any],
    run_command_text_result_fn: Callable[..., Any],
    configure_model_selection_fn: Callable[..., Any],
    configure_route_selection_fn: Callable[..., Any],
    configure_delegate_selection_fn: Callable[..., Any],
) -> None:
    runtime_cls._restore_provider_state = restore_provider_state_fn
    runtime_cls.start_thread = start_thread_fn
    runtime_cls.resume_thread = resume_thread_fn
    runtime_cls.configure_runtime_policy = configure_runtime_policy_fn
    runtime_cls.handle_prompt = handle_prompt_fn
    runtime_cls._run_command_text_result = run_command_text_result_fn
    runtime_cls.configure_model_selection = configure_model_selection_fn
    runtime_cls.configure_route_selection = configure_route_selection_fn
    runtime_cls.configure_delegate_selection = configure_delegate_selection_fn


__all__ = [
    "bind_runtime_override_methods",
    "build_configure_delegate_selection_with_provider_availability_refresh",
    "build_configure_model_selection_with_provider_availability_refresh",
    "build_configure_route_selection_with_provider_availability_refresh",
    "build_configure_runtime_policy_with_workspace_context_sync",
    "build_handle_prompt_with_request_user_input_sync",
    "build_restore_provider_state_with_request_user_input_sync",
    "build_resume_thread_with_workspace_context_sync",
    "build_run_command_text_result_with_request_user_input_sync",
    "build_start_thread_with_workspace_context_sync",
    "capture_original_runtime_override_methods",
]
