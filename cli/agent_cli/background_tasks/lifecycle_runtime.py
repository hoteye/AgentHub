from __future__ import annotations

from typing import Any

TERMINAL_BACKGROUND_TASK_STATES = frozenset({"completed", "failed", "cancelled"})
_QUEUE_LIFECYCLE_EVENTS = {
    "queued": "dispatch_queued",
    "running": "dispatch_claimed",
    "completed": "dispatch_completed",
    "failed": "dispatch_failed",
    "cancelled": "dispatch_cancelled",
}
_PRESERVED_QUEUED_EVENTS = {"manual_retry_restore", "cleanup_requeue"}


def is_terminal_background_task_state(value: str) -> bool:
    return str(value or "").strip().lower() in TERMINAL_BACKGROUND_TASK_STATES


def normalized_queue_state(*, queue_state: str, result_status: str = "") -> str:
    normalized_queue = str(queue_state or "").strip().lower()
    if normalized_queue:
        return normalized_queue
    return str(result_status or "").strip().lower()


def lifecycle_last_event(
    *,
    queue_state: str,
    cancel_requested: bool,
    existing_event: str = "",
) -> str:
    normalized_queue = str(queue_state or "").strip().lower()
    normalized_existing = str(existing_event or "").strip().lower()
    if normalized_existing in _PRESERVED_QUEUED_EVENTS and normalized_queue == "queued" and not cancel_requested:
        return normalized_existing
    if cancel_requested and not is_terminal_background_task_state(normalized_queue):
        return "cancel_requested"
    return _QUEUE_LIFECYCLE_EVENTS.get(normalized_queue, normalized_existing)


def normalize_artifact(
    *,
    artifact: dict[str, Any] | None,
    task_type: str = "",
    dispatch_id: int = 0,
    queue_state: str = "",
    cancel_requested: bool = False,
    provider: str = "",
    queue_source_of_truth: str = "dispatch",
) -> dict[str, Any]:
    updated = dict(artifact or {})
    normalized_queue = normalized_queue_state(
        queue_state=queue_state or str(updated.get("queue_state") or ""),
    )
    normalized_cancel_requested = bool(cancel_requested)
    if task_type:
        updated["task_type"] = str(task_type)
    if int(dispatch_id or 0) > 0:
        updated["dispatch_id"] = int(dispatch_id)
    if normalized_queue:
        updated["queue_state"] = normalized_queue
    updated["cancel_requested"] = normalized_cancel_requested
    if provider:
        updated.setdefault("provider", str(provider))
    if queue_source_of_truth:
        updated["queue_source_of_truth"] = str(queue_source_of_truth)
    lifecycle_event = lifecycle_last_event(
        queue_state=normalized_queue,
        cancel_requested=normalized_cancel_requested,
        existing_event=str(updated.get("lifecycle_last_event") or ""),
    )
    if lifecycle_event:
        updated["lifecycle_last_event"] = lifecycle_event
    else:
        updated.pop("lifecycle_last_event", None)
    return updated
