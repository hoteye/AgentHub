from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli.runtime_services import delegated_agent_result_contract_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime


def _preview_text(value: Any, *, max_chars: int = 240) -> str:
    return delegated_agent_result_contract_runtime.preview_text(value, max_chars=max_chars)


def _workspace_root(runtime: Any) -> Path:
    return delegated_agent_result_contract_runtime.workspace_root(runtime)


def _looks_like_windows_abs_path(text: str) -> bool:
    return delegated_agent_result_contract_runtime.looks_like_windows_abs_path(text)


def _normalize_delegated_path(runtime: Any, candidate: Any) -> str:
    return delegated_agent_result_contract_runtime.normalize_delegated_path(runtime, candidate)


def _parse_structured_result(text: str) -> Any | None:
    return delegated_agent_result_contract_runtime.parse_structured_result(text)


def _delegated_result_artifact(*, status: str, assistant_text: str, error: str) -> Dict[str, Any]:
    return delegated_agent_result_contract_runtime.delegated_result_artifact(
        status=status,
        assistant_text=assistant_text,
        error=error,
    )


def _delegated_result_confidence(*, status: str, artifact: Dict[str, Any], touched_scope: List[str]) -> str:
    return delegated_agent_result_contract_runtime.delegated_result_confidence(
        status=status,
        artifact=artifact,
        touched_scope=touched_scope,
    )


def _parse_runtime_iso(value: Any) -> datetime | None:
    return delegated_agent_workflow_runtime.parse_runtime_iso(value)


def _now_utc() -> datetime:
    return delegated_agent_workflow_runtime.now_utc()


def _elapsed_ms(started_at: Any, ended_at: Any = None) -> int | None:
    return delegated_agent_workflow_runtime.elapsed_ms(started_at, ended_at)


def delegated_parallel_group(task_shape: Any) -> str:
    return delegated_agent_workflow_runtime.delegated_parallel_group(task_shape)


def delegated_parallel_limit(
    parallel_group: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> int:
    return delegated_agent_workflow_runtime.delegated_parallel_limit(
        parallel_group,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
    )


def delegated_session_is_active(session: Any) -> bool:
    return delegated_agent_workflow_runtime.delegated_session_is_active(session)


def delegated_result_status(session: Any) -> str:
    return delegated_agent_workflow_runtime.delegated_result_status(session)


def delegated_completion_policy(
    *,
    role: Any,
    delegation_mode: Any,
    wait_required: Any,
) -> str:
    return delegated_agent_workflow_runtime.delegated_completion_policy(
        role=role,
        delegation_mode=delegation_mode,
        wait_required=wait_required,
    )


def delegated_background_priority(
    *,
    role: Any,
    delegation_mode: Any,
    wait_required: Any,
) -> str:
    return delegated_agent_workflow_runtime.delegated_background_priority(
        role=role,
        delegation_mode=delegation_mode,
        wait_required=wait_required,
    )


def delegated_completion_state(
    *,
    status: Any,
    adopted: bool,
    completion_policy: str,
) -> str:
    return delegated_agent_workflow_runtime.delegated_completion_state(
        status=status,
        adopted=adopted,
        completion_policy=completion_policy,
    )


def delegated_result_state(
    *,
    status: Any,
    completion_state: str,
    adopted: bool,
) -> str:
    return delegated_agent_workflow_runtime.delegated_result_state(
        status=status,
        completion_state=completion_state,
        adopted=adopted,
    )


def delegated_terminal_state(
    *,
    status: Any,
    terminal_reason: Any,
    has_text: bool,
) -> str:
    return delegated_agent_workflow_runtime.delegated_terminal_state(
        status=status,
        terminal_reason=terminal_reason,
        has_text=has_text,
    )


def collect_delegated_paths(runtime: Any, value: Any, depth: int = 0, *, path_hint: bool = False) -> List[str]:
    return delegated_agent_result_contract_runtime.collect_delegated_paths(
        runtime,
        value,
        depth=depth,
        path_hint=path_hint,
    )
