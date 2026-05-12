from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core import background_task_commands_logic_runtime as background_task_commands_logic_runtime_service
from cli.agent_cli.runtime_core import background_task_commands_text_runtime as background_task_commands_text_runtime_service


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
