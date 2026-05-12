from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services import delegated_agent_background_runtime as delegated_agent_background_runtime_service
from cli.agent_cli.runtime_services import delegated_agent_session_runtime as delegated_agent_session_runtime_service
from cli.agent_cli.runtime_services import delegated_agent_turn_runtime as delegated_agent_turn_runtime_service
from cli.agent_cli.runtime_services import delegated_agent_workflow as delegated_agent_workflow_service


def build_delegated_background_turn_methods(
    *,
    session_class: type[Any],
    now_iso_fn: Callable[[], str],
    preview_text_fn: Callable[..., str],
    build_background_task_adapter_fn: Callable[..., Any],
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> Dict[str, Any]:
    def _resolved_background_task_adapter_builder(self: Any) -> Callable[..., Any]:
        resolver = getattr(self, "_resolve_background_task_adapter_builder", None)
        if callable(resolver):
            resolved = resolver()
            if callable(resolved):
                return resolved
        return build_background_task_adapter_fn

    def _background_task_adapter(self: Any):
        return delegated_agent_background_runtime_service.background_task_adapter(
            self,
            build_background_task_adapter_fn=_resolved_background_task_adapter_builder(self),
        )

    def _background_task_adapter_if_enabled(self: Any):
        return delegated_agent_background_runtime_service.background_task_adapter_if_enabled(self)

    @staticmethod
    def _delegated_background_task_id(session: Any) -> str:
        return delegated_agent_background_runtime_service.delegated_background_task_id(session)

    @staticmethod
    def _delegated_background_task_status(
        status: str,
        *,
        has_text: bool,
        terminal_reason: str = "",
    ) -> str:
        return delegated_agent_background_runtime_service.delegated_background_task_status(
            status,
            has_text=has_text,
            terminal_reason=terminal_reason,
        )

    @staticmethod
    def _delegated_background_notification_state(
        *,
        status: str,
        adopted: bool,
        terminal_reason: str,
    ) -> str:
        return delegated_agent_background_runtime_service.delegated_background_notification_state(
            status=status,
            adopted=adopted,
            terminal_reason=terminal_reason,
        )

    def _sync_delegated_background_task(self: Any, session: Any) -> None:
        delegated_agent_background_runtime_service.sync_delegated_background_task(
            self,
            session,
            preview_text_fn=preview_text_fn,
        )

    def _record_orphaned_delegated_background_task(
        self: Any,
        raw_session: Dict[str, Any],
        *,
        reason: str,
        error: str = "",
    ) -> None:
        delegated_agent_background_runtime_service.record_orphaned_delegated_background_task(
            self,
            raw_session,
            reason=reason,
            error=error,
            preview_text_fn=preview_text_fn,
            now_iso_fn=now_iso_fn,
        )

    def _request_delegated_session_cleanup(
        self: Any,
        session: Any,
        *,
        reason: str,
        summary: str,
    ) -> bool:
        return delegated_agent_background_runtime_service.request_delegated_session_cleanup(
            self,
            session,
            reason=reason,
            summary=summary,
            now_iso_fn=now_iso_fn,
        )

    def _cleanup_delegated_sessions_for_role(self: Any, role_name: str, *, reason: str) -> int:
        return delegated_agent_background_runtime_service.cleanup_delegated_sessions_for_role(
            self,
            role_name,
            reason=reason,
        )

    def _delegated_agent_payload(self: Any, session: Any) -> Dict[str, Any]:
        return delegated_agent_workflow_service.delegated_agent_payload(
            self,
            session,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
        )

    def _delegated_workflow_payload(
        self: Any,
        session: Any,
        *,
        steps_limit: int = 8,
        checkpoints_limit: int = 8,
    ) -> Dict[str, Any]:
        return delegated_agent_workflow_service.delegated_workflow_payload(
            self,
            session,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
            steps_limit=steps_limit,
            checkpoints_limit=checkpoints_limit,
        )

    def _delegated_workflow_text(self: Any, payload: Dict[str, Any]) -> str:
        return delegated_agent_workflow_service.delegated_workflow_text(payload)

    def _delegated_agent_summary_text(self: Any, session: Any) -> str:
        return delegated_agent_workflow_service.delegated_agent_summary_text(
            self,
            session,
            max_active=max_active,
            read_only_max_active=read_only_max_active,
            long_running_max_active=long_running_max_active,
        )

    @staticmethod
    def _delegated_agent_id() -> str:
        return delegated_agent_session_runtime_service.delegated_agent_id()

    @staticmethod
    def _delegated_queue_item(
        message: str,
        *,
        interrupt: bool = False,
        step_id: str = "",
        input_items: list[dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        return delegated_agent_session_runtime_service.delegated_queue_item(
            message,
            interrupt=interrupt,
            step_id=step_id,
            input_items=input_items,
        )

    @staticmethod
    def _normalized_delegated_queue_item(item: Any) -> Dict[str, Any] | None:
        return delegated_agent_session_runtime_service.normalized_delegated_queue_item(item)

    def _snapshot_delegated_agent_session(self: Any, session: Any) -> Dict[str, Any]:
        return delegated_agent_background_runtime_service.snapshot_delegated_agent_session(self, session)

    def _delegated_agent_state_snapshot(self: Any) -> List[Dict[str, Any]]:
        return delegated_agent_background_runtime_service.delegated_agent_state_snapshot(self)

    @staticmethod
    def _restored_delegated_status(
        *,
        status: Any,
        queued_inputs: List[Dict[str, Any]],
        close_requested: bool,
        closed: bool,
        assistant_text: str,
        error: str,
    ) -> str:
        return delegated_agent_background_runtime_service.restored_delegated_status(
            status=status,
            queued_inputs=queued_inputs,
            close_requested=close_requested,
            closed=closed,
            assistant_text=assistant_text,
            error=error,
        )

    def _reset_delegated_agent_state(self: Any) -> None:
        delegated_agent_background_runtime_service.reset_delegated_agent_state(self)

    def _restore_delegated_agent_state(self: Any, state: Dict[str, Any]) -> None:
        delegated_agent_background_runtime_service.restore_delegated_agent_state(
            self,
            state,
            session_class=session_class,
            now_iso_fn=now_iso_fn,
        )

    def _delegated_session(self: Any, agent_id: str) -> Any:
        return delegated_agent_session_runtime_service.delegated_session(self, agent_id)

    def _delegated_plan_kwargs(self: Any, planner: Any, *, session: Any) -> Dict[str, Any]:
        return delegated_agent_turn_runtime_service.delegated_plan_kwargs(
            self,
            planner,
            session=session,
        )

    def _run_delegated_agent_turn(self: Any, session: Any, *, user_text: str) -> CommandExecutionResult:
        return delegated_agent_turn_runtime_service.run_delegated_agent_turn(
            self,
            session,
            user_text=user_text,
        )

    def _apply_delegated_turn_result(
        self: Any,
        session: Any,
        *,
        user_text: str,
        step_id: str = "",
        result: CommandExecutionResult,
    ) -> None:
        delegated_agent_turn_runtime_service.apply_delegated_turn_result(
            self,
            session,
            user_text=user_text,
            step_id=step_id,
            result=result,
        )

    def _apply_interrupted_delegated_turn_result(
        self: Any,
        session: Any,
        *,
        user_text: str,
        step_id: str = "",
        result: CommandExecutionResult,
    ) -> None:
        delegated_agent_turn_runtime_service.apply_interrupted_delegated_turn_result(
            self,
            session,
            user_text=user_text,
            step_id=step_id,
            result=result,
        )

    def _start_delegated_agent_worker(self: Any, session: Any) -> None:
        delegated_agent_session_runtime_service.start_delegated_agent_worker(self, session)

    def _run_delegated_agent_worker(self: Any, agent_id: str) -> None:
        delegated_agent_turn_runtime_service.run_delegated_agent_worker(
            self,
            agent_id,
        )

    def _create_delegated_agent_session(
        self: Any,
        *,
        task_text: str,
        role: str,
        resolution: Any,
        metadata: Dict[str, Any] | None = None,
    ) -> Any:
        return delegated_agent_session_runtime_service.create_delegated_agent_session(
            self,
            session_class=session_class,
            task_text=task_text,
            role=role,
            resolution=resolution,
            metadata=metadata,
        )

    return {
        "_background_task_adapter": _background_task_adapter,
        "_background_task_adapter_if_enabled": _background_task_adapter_if_enabled,
        "_delegated_background_task_id": _delegated_background_task_id,
        "_delegated_background_task_status": _delegated_background_task_status,
        "_delegated_background_notification_state": _delegated_background_notification_state,
        "_sync_delegated_background_task": _sync_delegated_background_task,
        "_record_orphaned_delegated_background_task": _record_orphaned_delegated_background_task,
        "_request_delegated_session_cleanup": _request_delegated_session_cleanup,
        "_cleanup_delegated_sessions_for_role": _cleanup_delegated_sessions_for_role,
        "_delegated_agent_payload": _delegated_agent_payload,
        "_delegated_workflow_payload": _delegated_workflow_payload,
        "_delegated_workflow_text": _delegated_workflow_text,
        "_delegated_agent_summary_text": _delegated_agent_summary_text,
        "_delegated_agent_id": _delegated_agent_id,
        "_delegated_queue_item": _delegated_queue_item,
        "_normalized_delegated_queue_item": _normalized_delegated_queue_item,
        "_snapshot_delegated_agent_session": _snapshot_delegated_agent_session,
        "_delegated_agent_state_snapshot": _delegated_agent_state_snapshot,
        "_restored_delegated_status": _restored_delegated_status,
        "_reset_delegated_agent_state": _reset_delegated_agent_state,
        "_restore_delegated_agent_state": _restore_delegated_agent_state,
        "_delegated_session": _delegated_session,
        "_delegated_plan_kwargs": _delegated_plan_kwargs,
        "_run_delegated_agent_turn": _run_delegated_agent_turn,
        "_apply_delegated_turn_result": _apply_delegated_turn_result,
        "_apply_interrupted_delegated_turn_result": _apply_interrupted_delegated_turn_result,
        "_start_delegated_agent_worker": _start_delegated_agent_worker,
        "_run_delegated_agent_worker": _run_delegated_agent_worker,
        "_create_delegated_agent_session": _create_delegated_agent_session,
    }
