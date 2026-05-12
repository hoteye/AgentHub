from __future__ import annotations

from typing import Any, Callable, Optional

from cli.agent_cli.runtime_core import background_task_commands_helpers_runtime as background_task_commands_helpers_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_logic_runtime as background_task_commands_logic_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_runtime as background_task_commands_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_helper_runtime as background_task_commands_helper_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_summary_runtime as background_task_commands_summary_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_text_runtime as background_task_commands_text_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_worker_runtime as background_task_commands_worker_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_actions_runtime as background_task_commands_actions_runtime_service
from cli.agent_cli.slash_parser import SlashInvocation


def _preview_text(value: Any, *, max_chars: int = 240) -> str:
    return background_task_commands_logic_runtime_service.preview_text(value, max_chars=max_chars)


def _parse_csv_paths(value: Any) -> list[str]:
    return background_task_commands_logic_runtime_service.parse_csv_paths(value)


def _parse_positive_float(value: Any, *, option_name: str) -> float:
    return background_task_commands_logic_runtime_service.parse_positive_float(value, option_name=option_name)


def _wait_summary_fragment(payload: dict[str, Any]) -> str:
    return background_task_commands_helper_runtime_service.wait_summary_fragment(payload)


def _background_tasks_text(runtime: Any, *, limit: int) -> str:
    return background_task_commands_helpers_runtime_service.background_tasks_text(
        runtime,
        limit=limit,
        preview_text_fn=_preview_text,
    )


def _background_worker_status_text(runtime: Any) -> str:
    return background_task_commands_helpers_runtime_service.background_worker_status_text(runtime)


def _background_worker_run_once_text(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.background_worker_run_once_text(
        runtime,
        raw_args=raw_args,
        parse_option_tokens_fn=_parse_option_tokens,
    )


def _background_worker_start_text(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.background_worker_start_text(
        runtime,
        raw_args=raw_args,
        parse_option_tokens_fn=_parse_option_tokens,
    )


def _background_worker_stop_text(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.background_worker_stop_text(runtime, raw_args=raw_args)


def _workflow_goal_text(payload: dict[str, Any]) -> str:
    return background_task_commands_helper_runtime_service.workflow_goal_text(payload)


def _delegated_workflows_text(runtime: Any, *, limit: int) -> tuple[list[str], set[str]]:
    return background_task_commands_helpers_runtime_service.delegated_workflows_text(
        runtime,
        limit=limit,
        preview_text_fn=_preview_text,
    )


def _orchestration_workflows_text(runtime: Any, *, limit: int) -> tuple[list[str], int]:
    return background_task_commands_helpers_runtime_service.orchestration_workflows_text(runtime, limit=limit)


def _execution_projection_counts(runtime: Any) -> dict[str, int]:
    return background_task_commands_helpers_runtime_service.execution_projection_counts(runtime)


def _workflows_text(runtime: Any, *, limit: int) -> str:
    return background_task_commands_helpers_runtime_service.workflows_text(
        runtime,
        limit=limit,
        preview_text_fn=_preview_text,
    )


def _submit_background_benchmark(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.submit_background_benchmark(
        runtime,
        raw_args=raw_args,
        parse_positive_float_fn=_parse_positive_float,
    )


def _submit_background_smoke(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.submit_background_smoke(
        runtime,
        raw_args=raw_args,
        parse_positive_float_fn=_parse_positive_float,
    )


def _submit_background_teammate(runtime: Any, *, raw_args: str) -> str:
    return background_task_commands_helpers_runtime_service.submit_background_teammate(
        runtime,
        raw_args=raw_args,
        parse_option_tokens_fn=_parse_option_tokens,
        parse_csv_paths_fn=_parse_csv_paths,
        parse_positive_float_fn=_parse_positive_float,
        preview_text_fn=_preview_text,
    )


def _background_task_status_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_actions_runtime_service.background_task_status_text(
        runtime,
        task_id=task_id,
    )


def _background_task_apply_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_actions_runtime_service.background_task_apply_text(
        runtime,
        task_id=task_id,
    )


def _background_task_reject_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_actions_runtime_service.background_task_reject_text(
        runtime,
        task_id=task_id,
    )


def _background_task_cancel_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_actions_runtime_service.background_task_cancel_text(
        runtime,
        task_id=task_id,
    )


def _background_task_retry_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_actions_runtime_service.background_task_retry_text(
        runtime,
        task_id=task_id,
    )


def _parse_option_tokens(
    raw_args: str,
    *,
    value_flags: set[str],
) -> tuple[list[str], dict[str, str]]:
    return background_task_commands_runtime_service.parse_option_tokens(
        raw_args,
        value_flags=value_flags,
    )


def handle_background_task_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
    int_option: Callable[..., int | None],
) -> Optional[tuple[str, list[Any]]]:
    return background_task_commands_runtime_service.handle_background_task_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        int_option=int_option,
        workflows_text_fn=_workflows_text,
        background_tasks_text_fn=_background_tasks_text,
        background_worker_status_text_fn=_background_worker_status_text,
        background_worker_start_text_fn=_background_worker_start_text,
        background_worker_stop_text_fn=_background_worker_stop_text,
        background_worker_run_once_text_fn=_background_worker_run_once_text,
        submit_background_benchmark_fn=_submit_background_benchmark,
        submit_background_smoke_fn=_submit_background_smoke,
        handle_background_teammate_fn=lambda runtime, arg_text, slash_invocation=None: background_task_commands_runtime_service.handle_background_teammate_command(
            runtime,
            arg_text=arg_text,
            parse_option_tokens_fn=_parse_option_tokens,
            parse_csv_paths_fn=_parse_csv_paths,
            parse_positive_float_fn=_parse_positive_float,
            submit_background_teammate_fn=_submit_background_teammate,
            slash_invocation=slash_invocation,
        ),
        background_task_status_text_fn=_background_task_status_text,
        background_task_cancel_text_fn=_background_task_cancel_text,
        background_task_retry_text_fn=_background_task_retry_text,
        background_task_apply_text_fn=_background_task_apply_text,
        background_task_reject_text_fn=_background_task_reject_text,
    )
