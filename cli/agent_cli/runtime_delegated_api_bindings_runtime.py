from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services import (
    delegated_agent_session_runtime as delegated_agent_session_runtime_service,
)


def bind_runtime_delegated_api_methods(
    runtime_cls: Any,
    *,
    session_class: type[Any],
) -> None:
    @staticmethod
    def _normalized_recover_action(action: str | None) -> str:
        return delegated_agent_session_runtime_service.normalized_recover_action(action)

    def agent_workflow_result(
        self: Any,
        agent_id: str,
        *,
        steps_limit: int = 8,
        checkpoints_limit: int = 8,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.agent_workflow_result(
            self,
            agent_id,
            steps_limit=steps_limit,
            checkpoints_limit=checkpoints_limit,
        )

    def recover_agent_result(
        self: Any,
        agent_id: str,
        *,
        action: str | None = None,
        step_id: str | None = None,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.recover_agent_result(
            self,
            agent_id,
            action=action,
            step_id=step_id,
        )

    def wait_agent_result(
        self: Any,
        agent_id: str,
        *,
        timeout_ms: Any = 30000,
        reason: str | None = None,
        wait_required: Any = None,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.wait_agent_result(
            self,
            agent_id,
            timeout_ms=timeout_ms,
            reason=reason,
            wait_required=wait_required,
        )

    def wait_agents_result(
        self: Any,
        agent_ids: list[str],
        *,
        timeout_ms: Any = 30000,
        reason: str | None = None,
        wait_required: Any = None,
        codex_style: bool = False,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.wait_agents_result(
            self,
            agent_ids,
            timeout_ms=timeout_ms,
            reason=reason,
            wait_required=wait_required,
            codex_style=codex_style,
        )

    def send_input_result(
        self: Any,
        agent_id: str,
        *,
        message: str,
        interrupt: bool = False,
        input_items: list[dict[str, Any]] | None = None,
        codex_style: bool = False,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.send_input_result(
            self,
            agent_id,
            message=message,
            interrupt=interrupt,
            input_items=input_items,
            codex_style=codex_style,
        )

    def close_agent_result(
        self: Any,
        agent_id: str,
        *,
        codex_style: bool = False,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.close_agent_result(
            self,
            agent_id,
            codex_style=codex_style,
        )

    def resume_agent_result(
        self: Any,
        agent_id: str,
        *,
        codex_style: bool = False,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.resume_agent_result(
            self,
            agent_id,
            codex_style=codex_style,
        )

    def spawn_agent_result(
        self: Any,
        *,
        task: str,
        role: str = "subagent",
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
        async_mode: bool | None = None,
        reason: str | None = None,
        mode: str | None = None,
        wait_required: Any = None,
        task_shape: str | None = None,
        subagent_type: str | None = None,
        input_items: list[dict[str, Any]] | None = None,
        fork_context: bool | None = None,
        codex_collab_payload: bool = False,
    ) -> CommandExecutionResult:
        return delegated_agent_session_runtime_service.spawn_agent_result(
            self,
            session_class=session_class,
            task=task,
            role=role,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            async_mode=async_mode,
            reason=reason,
            mode=mode,
            wait_required=wait_required,
            task_shape=task_shape,
            subagent_type=subagent_type,
            input_items=input_items,
            fork_context=fork_context,
            codex_collab_payload=codex_collab_payload,
        )

    runtime_cls._normalized_recover_action = _normalized_recover_action
    runtime_cls.agent_workflow_result = agent_workflow_result
    runtime_cls.recover_agent_result = recover_agent_result
    runtime_cls.wait_agent_result = wait_agent_result
    runtime_cls.wait_agents_result = wait_agents_result
    runtime_cls.send_input_result = send_input_result
    runtime_cls.close_agent_result = close_agent_result
    runtime_cls.resume_agent_result = resume_agent_result
    runtime_cls.spawn_agent_result = spawn_agent_result
