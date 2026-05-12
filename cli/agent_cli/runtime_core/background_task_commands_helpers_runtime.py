from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import background_task_commands_helper_runtime as background_task_commands_helper_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_helpers_runtime_tasks as background_task_commands_helpers_runtime_tasks_service
from cli.agent_cli.runtime_core import background_task_commands_logic_runtime as background_task_commands_logic_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_runtime as background_task_commands_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_summary_runtime as background_task_commands_summary_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_text_runtime as background_task_commands_text_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_worker_runtime as background_task_commands_worker_runtime_service


def background_tasks_text(runtime: Any, *, limit: int, preview_text_fn: Callable[..., str]) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_tasks_text(
        runtime,
        limit=limit,
        preview_text_fn=preview_text_fn,
    )


def background_worker_status_text(runtime: Any) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_worker_status_text(runtime)


def background_worker_run_once_text(
    runtime: Any,
    *,
    raw_args: str,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter
    from cli.agent_cli.background_tasks.worker_entry import run_worker_once

    try:
        max_jobs, stale_after_seconds = background_task_commands_runtime_service.parse_background_worker_run_once_args(
            raw_args,
            parse_option_tokens_fn=parse_option_tokens_fn,
        )
    except ValueError as exc:
        return str(exc)
    processed = int(
        run_worker_once(
            cwd=getattr(runtime, "cwd", None),
            max_jobs=max_jobs,
            stale_after_seconds=stale_after_seconds,
        )
        or 0
    )
    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.worker_status() if hasattr(adapter, "worker_status") else {}
    return background_task_commands_worker_runtime_service.background_worker_run_once_text(
        processed=processed,
        max_jobs=max_jobs,
        stale_after_seconds=stale_after_seconds,
        payload=payload if isinstance(payload, dict) else None,
    )


def background_worker_start_text(
    runtime: Any,
    *,
    raw_args: str,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
) -> str:
    from cli.agent_cli.background_tasks.worker_entry import start_worker_process

    try:
        max_jobs, poll_interval, stale_after_seconds = background_task_commands_runtime_service.parse_background_worker_start_args(
            raw_args,
            parse_option_tokens_fn=parse_option_tokens_fn,
        )
    except ValueError as exc:
        return str(exc)
    payload = start_worker_process(
        cwd=getattr(runtime, "cwd", None),
        max_jobs=max_jobs,
        poll_interval=poll_interval,
        stale_after_seconds=stale_after_seconds,
    )
    return background_task_commands_worker_runtime_service.background_worker_start_text(
        max_jobs=max_jobs,
        poll_interval=poll_interval,
        stale_after_seconds=stale_after_seconds,
        payload=payload,
    )


def background_worker_stop_text(runtime: Any, *, raw_args: str) -> str:
    from cli.agent_cli.background_tasks.worker_entry import stop_worker_process

    try:
        force = background_task_commands_runtime_service.parse_background_worker_stop_args(raw_args)
    except ValueError as exc:
        return str(exc)
    payload = stop_worker_process(
        cwd=getattr(runtime, "cwd", None),
        force=force,
    )
    return background_task_commands_worker_runtime_service.background_worker_stop_text(
        force=force,
        payload=payload,
    )


def delegated_workflows_text(
    runtime: Any,
    *,
    limit: int,
    preview_text_fn: Callable[..., str],
) -> tuple[list[str], set[str]]:
    snapshot_fn = getattr(runtime, "_delegated_agent_state_snapshot", None)
    if not callable(snapshot_fn):
        return ([], set())
    try:
        raw_items = snapshot_fn()
    except Exception:
        return ([], set())
    items = [dict(item) for item in list(raw_items or []) if isinstance(item, dict)]
    return background_task_commands_logic_runtime_service.delegated_workflow_projection(
        items,
        limit=limit,
        delegated_workflow_line_fn=background_task_commands_helper_runtime_service.delegated_workflow_line,
        preview_text_fn=preview_text_fn,
    )


def orchestration_workflows_text(runtime: Any, *, limit: int) -> tuple[list[str], int]:
    list_fn = getattr(runtime, "list_orchestration_workflows", None)
    if not callable(list_fn):
        return ([], 0)
    try:
        lines, count = list_fn(limit=limit)
    except Exception:
        return ([], 0)
    normalized_lines = [str(item) for item in list(lines or []) if str(item or "").strip()]
    return (normalized_lines, max(0, int(count)))


def execution_projection_counts(runtime: Any) -> dict[str, int]:
    manager = getattr(runtime, "run_manager", None)
    list_fn = getattr(manager, "list", None)
    if not callable(list_fn):
        return {}
    try:
        items = list_fn()
    except Exception:
        return {}
    return background_task_commands_summary_runtime_service.execution_projection_counts(list(items or []))


def workflows_text(runtime: Any, *, limit: int, preview_text_fn: Callable[..., str]) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    delegated_lines, mirrored_task_ids = delegated_workflows_text(runtime, limit=limit, preview_text_fn=preview_text_fn)
    orchestration_lines, orchestration_count = orchestration_workflows_text(runtime, limit=limit)
    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    background_items = list(adapter.list_recent(limit=max(1, int(limit)) * 4))
    background_lines, mirrored_count = background_task_commands_logic_runtime_service.background_workflow_projection(
        background_items,
        limit=limit,
        mirrored_task_ids=mirrored_task_ids,
        background_workflow_line_fn=background_task_commands_helper_runtime_service.background_workflow_line,
        preview_text_fn=preview_text_fn,
    )
    return background_task_commands_summary_runtime_service.workflows_text(
        delegated_lines=delegated_lines,
        orchestration_lines=orchestration_lines,
        background_lines=background_lines,
        orchestration_count=orchestration_count,
        mirrored_count=mirrored_count,
        background_enabled=bool(adapter.config.enabled),
        execution_projection_counts=execution_projection_counts(runtime),
    )


def submit_background_benchmark(
    runtime: Any,
    *,
    raw_args: str,
    parse_positive_float_fn: Callable[..., float],
) -> str:
    from cli.agent_cli.background_tasks import enqueue_background_task

    try:
        argv, timeout_payload = background_task_commands_helper_runtime_service.parse_background_benchmark_args(
            raw_args,
            parse_positive_float_fn=parse_positive_float_fn,
        )
    except ValueError as exc:
        return str(exc)
    enqueue_payload, detail_pairs = background_task_commands_logic_runtime_service.benchmark_enqueue_payload(
        argv,
        timeout_payload,
    )
    handle = enqueue_background_task(
        task_type="benchmark",
        payload=enqueue_payload,
        source="cli",
        cwd=getattr(runtime, "cwd", None),
        force_enable=True,
        metadata={"reason": "slash_command"},
    )
    return background_task_commands_text_runtime_service.submitted_task_text(
        title="background benchmark submitted",
        handle=handle,
        detail_pairs=detail_pairs,
    )


def submit_background_smoke(
    runtime: Any,
    *,
    raw_args: str,
    parse_positive_float_fn: Callable[..., float],
) -> str:
    from cli.agent_cli.background_tasks import enqueue_background_task

    try:
        kind, forwarded, timeout_payload = background_task_commands_helper_runtime_service.parse_background_smoke_args(
            raw_args,
            parse_positive_float_fn=parse_positive_float_fn,
        )
    except ValueError as exc:
        return str(exc)
    enqueue_payload, detail_pairs = background_task_commands_logic_runtime_service.smoke_enqueue_payload(
        kind=kind,
        forwarded=forwarded,
        runtime_cwd=str(getattr(runtime, "cwd", "") or ""),
        timeout_payload=timeout_payload,
    )
    handle = enqueue_background_task(
        task_type="smoke",
        payload=enqueue_payload,
        source="cli",
        cwd=getattr(runtime, "cwd", None),
        force_enable=True,
        metadata={"reason": "slash_command"},
    )
    return background_task_commands_text_runtime_service.submitted_task_text(
        title="background smoke submitted",
        handle=handle,
        detail_pairs=detail_pairs,
    )


def submit_background_teammate(
    runtime: Any,
    *,
    raw_args: str,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
    parse_csv_paths_fn: Callable[[Any], list[str]],
    parse_positive_float_fn: Callable[..., float],
    preview_text_fn: Callable[..., str],
) -> str:
    from cli.agent_cli.background_tasks import enqueue_background_task

    try:
        parsed = background_task_commands_summary_runtime_service.parse_background_teammate_args(
            raw_args,
            runtime_cwd=getattr(runtime, "cwd", ""),
            parse_option_tokens_fn=parse_option_tokens_fn,
            parse_csv_paths_fn=parse_csv_paths_fn,
            parse_positive_float_fn=parse_positive_float_fn,
        )
    except ValueError as exc:
        return str(exc)
    task_text = str(parsed["task_text"])
    provider = str(parsed["provider"])
    model = str(parsed["model"])
    reasoning_effort = str(parsed["reasoning_effort"])
    sandbox_mode = str(parsed["sandbox_mode"])
    allowed_paths = list(parsed["allowed_paths"])
    blocked_paths = list(parsed["blocked_paths"])
    timeout_payload = dict(parsed["timeout_payload"])
    if sandbox_mode == "workspace-write":
        event = runtime.request_background_teammate_approval(
            task_text,
            **background_task_commands_summary_runtime_service.background_teammate_approval_kwargs(
                parsed,
                queue_cwd=str(getattr(runtime, "cwd", "") or "").strip(),
            ),
        )
        payload = event.payload or {}
        return str(payload.get("summary_text") or "background teammate approval requested")
    enqueue_payload, metadata = background_task_commands_summary_runtime_service.background_teammate_enqueue_payload(parsed)
    handle = enqueue_background_task(
        task_type="teammate",
        payload=enqueue_payload,
        source="cli",
        cwd=getattr(runtime, "cwd", None),
        force_enable=True,
        metadata=metadata,
    )
    return background_task_commands_text_runtime_service.background_teammate_submission_text(
        handle=handle,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        timeout_seconds=timeout_payload.get("timeout_seconds"),
        task_text=task_text,
        preview_text_fn=preview_text_fn,
    )


def background_task_status_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_task_status_text(
        runtime,
        task_id=task_id,
    )


def background_task_apply_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_task_apply_text(
        runtime,
        task_id=task_id,
    )


def background_task_reject_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_task_reject_text(
        runtime,
        task_id=task_id,
    )


def background_task_cancel_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_task_cancel_text(
        runtime,
        task_id=task_id,
    )


def background_task_retry_text(runtime: Any, *, task_id: str) -> str:
    return background_task_commands_helpers_runtime_tasks_service.background_task_retry_text(
        runtime,
        task_id=task_id,
    )
