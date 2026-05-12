from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import background_task_commands_helper_runtime as background_task_commands_helper_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_logic_runtime as background_task_commands_logic_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_summary_runtime as background_task_commands_summary_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_text_runtime as background_task_commands_text_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_worker_runtime as background_task_commands_worker_runtime_service


def background_tasks_text(runtime: Any, *, limit: int, preview_text_fn: Callable[..., str]) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    items = adapter.list_recent(limit=limit)
    worker_payload = adapter.worker_status() if hasattr(adapter, "worker_status") else None
    item_lines = background_task_commands_logic_runtime_service.background_task_lines(
        items,
        get_status_fn=adapter.get_status if hasattr(adapter, "get_status") else None,
        overview_line_fn=background_task_commands_helper_runtime_service.background_task_overview_line,
        preview_text_fn=preview_text_fn,
    )
    return background_task_commands_summary_runtime_service.background_tasks_text(
        item_count=len(items),
        enabled=bool(adapter.config.enabled),
        provider=str(adapter.config.provider),
        queue_provider_label=str(adapter.queue.provider_label),
        worker_payload=worker_payload if isinstance(worker_payload, dict) else None,
        item_lines=item_lines,
    )


def background_worker_status_text(runtime: Any) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.worker_status() if hasattr(adapter, "worker_status") else {}
    return background_task_commands_worker_runtime_service.background_worker_status_text(
        enabled=bool(adapter.config.enabled),
        provider=str(adapter.config.provider),
        queue_provider_label=str(adapter.queue.provider_label),
        payload=payload if isinstance(payload, dict) else None,
    )


def background_task_status_text(runtime: Any, *, task_id: str) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.get_status(task_id)
    return background_task_commands_logic_runtime_service.task_payload_text(
        payload,
        task_id=task_id,
        not_found_text=f"background task not found: {task_id}",
        text_fn=background_task_commands_text_runtime_service.background_task_status_text,
    )


def background_task_apply_text(runtime: Any, *, task_id: str) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.apply_staged_changes(task_id) if hasattr(adapter, "apply_staged_changes") else None
    return background_task_commands_logic_runtime_service.task_payload_text(
        payload,
        task_id=task_id,
        not_found_text=f"background task not found: {task_id}",
        no_review_text=f"background task has no staged workspace review: {task_id}",
        text_fn=background_task_commands_text_runtime_service.background_task_apply_text,
    )


def background_task_reject_text(runtime: Any, *, task_id: str) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.reject_staged_changes(task_id) if hasattr(adapter, "reject_staged_changes") else None
    return background_task_commands_logic_runtime_service.task_payload_text(
        payload,
        task_id=task_id,
        not_found_text=f"background task not found: {task_id}",
        no_review_text=f"background task has no staged workspace review: {task_id}",
        text_fn=background_task_commands_text_runtime_service.background_task_reject_text,
    )


def background_task_cancel_text(runtime: Any, *, task_id: str) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.cancel(task_id)
    return background_task_commands_logic_runtime_service.task_payload_text(
        payload,
        task_id=task_id,
        not_found_text=f"background task not found: {task_id}",
        text_fn=background_task_commands_text_runtime_service.background_task_cancel_text,
    )


def background_task_retry_text(runtime: Any, *, task_id: str) -> str:
    from cli.agent_cli.background_tasks import build_background_task_adapter

    adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    payload = adapter.retry(task_id)
    return background_task_commands_logic_runtime_service.task_payload_text(
        payload,
        task_id=task_id,
        not_found_text=f"background task not found: {task_id}",
        text_fn=background_task_commands_text_runtime_service.background_task_retry_text,
    )
