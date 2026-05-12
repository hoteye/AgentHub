from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli import (
    runtime_delegated_background_turn_bindings_runtime as runtime_delegated_background_turn_bindings_runtime_service,
)
from cli.agent_cli import (
    runtime_delegated_binding_assign_runtime as runtime_delegated_binding_assign_runtime_service,
)
from cli.agent_cli.runtime_services import delegated_agent_session_runtime as delegated_agent_session_runtime_service
from cli.agent_cli.runtime_services import delegated_agent_workflow as delegated_agent_workflow_service
from cli.agent_cli.runtime_services import delegation_runtime as delegation_runtime_service
from cli.agent_cli.runtime_services import runtime_context_runtime as runtime_context_runtime_service


def bind_runtime_delegated_methods(
    runtime_cls: Any,
    *,
    session_class: type[Any],
    now_iso_fn: Callable[[], str],
    preview_text_fn: Callable[..., str],
    build_background_task_adapter_fn: Callable[..., Any],
    build_planner_fn: Callable[..., Any],
    current_host_platform_fn: Callable[[], str],
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> None:
    def _workspace_skill_roots(self: Any) -> List[str]:
        return runtime_context_runtime_service.workspace_skill_roots(self)

    @staticmethod
    def _provider_config_with_model_timeout(config: Any, timeout: int | None) -> Any:
        return delegated_agent_session_runtime_service.provider_config_with_model_timeout(
            config,
            timeout,
        )

    def _delegated_planner(self: Any, config: Any, *, timeout: int | None = None) -> Any:
        return delegated_agent_session_runtime_service.delegated_planner(
            self,
            config,
            timeout=timeout,
            build_planner_fn=build_planner_fn,
            current_host_platform_fn=current_host_platform_fn,
        )

    @staticmethod
    def _delegated_parallel_group(task_shape: Any) -> str:
        return delegated_agent_workflow_service.delegated_parallel_group(task_shape)

    @staticmethod
    def _delegated_parallel_limit(parallel_group: Any) -> int:
        return delegated_agent_workflow_service.delegated_parallel_limit(
            parallel_group,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
        )

    @staticmethod
    def _delegated_session_is_active(session: Any) -> bool:
        return delegated_agent_workflow_service.delegated_session_is_active(session)

    def _delegated_goal_text(self: Any, session: Any) -> str:
        return delegated_agent_workflow_service.delegated_goal_text(self, session)

    def _delegated_result_status(self: Any, session: Any) -> str:
        return delegated_agent_workflow_service.delegated_result_status(session)

    @staticmethod
    def _delegated_completion_policy(*, role: Any, delegation_mode: Any, wait_required: Any) -> str:
        return delegated_agent_workflow_service.delegated_completion_policy(
            role=role,
            delegation_mode=delegation_mode,
            wait_required=wait_required,
        )

    @staticmethod
    def _delegated_completion_state(*, status: Any, adopted: bool, completion_policy: str) -> str:
        return delegated_agent_workflow_service.delegated_completion_state(
            status=status,
            adopted=adopted,
            completion_policy=completion_policy,
        )

    @staticmethod
    def _delegated_background_priority(*, role: Any, delegation_mode: Any, wait_required: Any) -> str:
        return delegated_agent_workflow_service.delegated_background_priority(
            role=role,
            delegation_mode=delegation_mode,
            wait_required=wait_required,
        )

    def _collect_delegated_paths(self: Any, value: Any, depth: int = 0) -> List[str]:
        return delegated_agent_workflow_service.collect_delegated_paths(self, value, depth=depth)

    def _delegated_result_contract_payload(
        self: Any,
        *,
        goal: str,
        status: str,
        assistant_text: str,
        error: str,
        adopted: bool,
        touched_sources: List[Any],
        role: str = "",
        delegation_mode: str = "",
        wait_required: bool | None = None,
    ) -> Dict[str, Any]:
        return delegated_agent_workflow_service.delegated_result_contract_payload(
            self,
            goal=goal,
            status=status,
            assistant_text=assistant_text,
            error=error,
            adopted=adopted,
            touched_sources=touched_sources,
            role=role,
            delegation_mode=delegation_mode,
            wait_required=wait_required,
        )

    def _delegated_result_contract(self: Any, session: Any) -> Dict[str, Any]:
        return delegated_agent_workflow_service.delegated_result_contract(self, session)

    def _delegated_result_ready(self: Any, session: Any) -> bool:
        return delegated_agent_workflow_service.delegated_result_ready(self, session)

    @staticmethod
    def _delegated_result_adoptable(session: Any) -> bool:
        return delegated_agent_session_runtime_service.delegated_result_adoptable(session)

    def _delegated_scheduler_decision(self: Any, session: Any) -> Dict[str, Any]:
        return delegated_agent_workflow_service.delegated_scheduler_decision(
            self,
            session,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
        )

    def _notify_delegated_scheduler(self: Any) -> None:
        delegated_agent_workflow_service.notify_delegated_scheduler(self)

    def _wait_for_delegated_slot(
        self: Any,
        session: Any,
        *,
        timeout: float = 0.25,
    ) -> Dict[str, Any]:
        return delegated_agent_workflow_service.wait_for_delegated_slot(
            self,
            session,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
            now_iso_fn=now_iso_fn,
            timeout=timeout,
        )

    def _mark_delegated_result_adopted(self: Any, session: Any) -> None:
        delegated_agent_session_runtime_service.mark_delegated_result_adopted(
            self,
            session,
            now_iso_fn=now_iso_fn,
        )

    @staticmethod
    def _delegated_step_id(session: Any) -> str:
        return delegation_runtime_service.delegated_step_id(session)

    def _queue_delegated_step(
        self: Any,
        session: Any,
        *,
        user_text: str,
        source: str,
        retry_of_step_id: str = "",
        retry_root_step_id: str = "",
        retry_attempt: int = 0,
    ) -> str:
        return delegation_runtime_service.queue_delegated_step(
            session,
            user_text=user_text,
            source=source,
            preview_text=preview_text_fn,
            now_iso=now_iso_fn,
            retry_of_step_id=retry_of_step_id,
            retry_root_step_id=retry_root_step_id,
            retry_attempt=retry_attempt,
        )

    @staticmethod
    def _delegated_step(session: Any, step_id: str) -> Dict[str, Any] | None:
        return delegation_runtime_service.delegated_step(session, step_id)

    @staticmethod
    def _delegated_queue_item_step_id(item: Any) -> str:
        return delegation_runtime_service.delegated_queue_item_step_id(item)

    def _resolved_delegated_current_step_id(self: Any, session: Any) -> str:
        return delegation_runtime_service.resolved_delegated_current_step_id(session)

    def _refresh_delegated_current_step_id(self: Any, session: Any) -> str:
        return delegation_runtime_service.refresh_delegated_current_step_id(session)

    def _update_delegated_step(
        self: Any,
        session: Any,
        *,
        step_id: str,
        status: str,
        summary: str,
        assistant_text: str = "",
        error: str = "",
        started: bool = False,
        finished: bool = False,
    ) -> None:
        delegation_runtime_service.update_delegated_step(
            session,
            step_id=step_id,
            status=status,
            summary=summary,
            now_iso=now_iso_fn,
            assistant_text=assistant_text,
            error=error,
            started=started,
            finished=finished,
        )

    @staticmethod
    def _delegated_step_retry_root_id(step: Dict[str, Any] | None) -> str:
        return delegation_runtime_service.delegated_step_retry_root_id(step)

    @staticmethod
    def _delegated_step_retry_attempt(step: Dict[str, Any] | None) -> int:
        return delegation_runtime_service.delegated_step_retry_attempt(step)

    def _next_delegated_retry_attempt(self: Any, session: Any, *, retry_root_step_id: str) -> int:
        return delegation_runtime_service.next_delegated_retry_attempt(
            session,
            retry_root_step_id=retry_root_step_id,
        )

    def _delegated_latest_recoverable_step(
        self: Any,
        session: Any,
        *,
        step_id: str = "",
    ) -> Dict[str, Any] | None:
        return delegation_runtime_service.delegated_latest_recoverable_step(
            session,
            step_id=step_id,
        )

    def _delegated_recovery_actions(self: Any, session: Any) -> List[Dict[str, Any]]:
        return delegation_runtime_service.delegated_recovery_actions(session)

    def _delegated_workflow_state(self: Any, session: Any) -> str:
        return delegation_runtime_service.delegated_workflow_state(session)

    def _delegated_progress_summary(
        self: Any,
        session: Any,
        *,
        include_history: bool = False,
    ) -> Dict[str, Any]:
        return delegation_runtime_service.delegated_progress_summary(
            session,
            include_history=include_history,
        )

    def _record_delegated_checkpoint(
        self: Any,
        session: Any,
        *,
        kind: str,
        status: str,
        summary: str,
        step_id: str = "",
    ) -> None:
        delegation_runtime_service.record_delegated_checkpoint(
            session,
            kind=kind,
            status=status,
            summary=summary,
            step_id=step_id,
            now_iso=now_iso_fn,
        )

    methods = runtime_delegated_background_turn_bindings_runtime_service.build_delegated_background_turn_methods(
        session_class=session_class,
        now_iso_fn=now_iso_fn,
        preview_text_fn=preview_text_fn,
        build_background_task_adapter_fn=build_background_task_adapter_fn,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
    )

    methods.update(
        {
            "_workspace_skill_roots": _workspace_skill_roots,
            "_provider_config_with_model_timeout": _provider_config_with_model_timeout,
            "_delegated_planner": _delegated_planner,
            "_delegated_parallel_group": _delegated_parallel_group,
            "_delegated_parallel_limit": _delegated_parallel_limit,
            "_delegated_session_is_active": _delegated_session_is_active,
            "_delegated_goal_text": _delegated_goal_text,
            "_delegated_result_status": _delegated_result_status,
            "_delegated_completion_policy": _delegated_completion_policy,
            "_delegated_completion_state": _delegated_completion_state,
            "_delegated_background_priority": _delegated_background_priority,
            "_collect_delegated_paths": _collect_delegated_paths,
            "_delegated_result_contract_payload": _delegated_result_contract_payload,
            "_delegated_result_contract": _delegated_result_contract,
            "_delegated_result_ready": _delegated_result_ready,
            "_delegated_result_adoptable": _delegated_result_adoptable,
            "_delegated_scheduler_decision": _delegated_scheduler_decision,
            "_notify_delegated_scheduler": _notify_delegated_scheduler,
            "_wait_for_delegated_slot": _wait_for_delegated_slot,
            "_mark_delegated_result_adopted": _mark_delegated_result_adopted,
            "_delegated_step_id": _delegated_step_id,
            "_queue_delegated_step": _queue_delegated_step,
            "_delegated_step": _delegated_step,
            "_delegated_queue_item_step_id": _delegated_queue_item_step_id,
            "_resolved_delegated_current_step_id": _resolved_delegated_current_step_id,
            "_refresh_delegated_current_step_id": _refresh_delegated_current_step_id,
            "_update_delegated_step": _update_delegated_step,
            "_delegated_step_retry_root_id": _delegated_step_retry_root_id,
            "_delegated_step_retry_attempt": _delegated_step_retry_attempt,
            "_next_delegated_retry_attempt": _next_delegated_retry_attempt,
            "_delegated_latest_recoverable_step": _delegated_latest_recoverable_step,
            "_delegated_recovery_actions": _delegated_recovery_actions,
            "_delegated_workflow_state": _delegated_workflow_state,
            "_delegated_progress_summary": _delegated_progress_summary,
            "_record_delegated_checkpoint": _record_delegated_checkpoint,
        }
    )
    runtime_delegated_binding_assign_runtime_service.assign_runtime_delegated_methods(
        runtime_cls,
        methods,
    )
