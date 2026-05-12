from __future__ import annotations

import json
from typing import Any, Callable


def submitted_task_text(
    *,
    title: str,
    handle: Any,
    detail_pairs: list[tuple[str, Any]],
) -> str:
    lines = [title]
    lines.append(f"task_id={handle.task_id}")
    lines.append(f"status={handle.status}")
    for key, value in detail_pairs:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, dict)):
            rendered = json.dumps(value, ensure_ascii=False)
        else:
            rendered = str(value)
        lines.append(f"{key}={rendered}")
    if str(getattr(handle, "job_id", "") or "").strip():
        lines.append(f"job_id={handle.job_id}")
    if str(getattr(handle, "provider", "") or "").strip():
        lines.append(f"provider={handle.provider}")
    return "\n".join(lines)


def background_task_apply_text(payload: dict[str, Any], *, task_id: str) -> str:
    artifact = dict(payload.get("artifact") or {})
    final_apply_state = str(artifact.get("final_apply_state") or "").strip()
    if final_apply_state == "applied":
        title = "background task changes applied"
    elif final_apply_state == "blocked":
        title = "background task apply blocked"
    else:
        title = "background task apply noop"
    lines = [title, f"task_id={task_id}"]
    for key in ("status", "summary", "error"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if final_apply_state:
        lines.append(f"final_apply_state={final_apply_state}")
    applied_files = artifact.get("applied_files")
    if applied_files is not None:
        lines.append(f"applied_files={json.dumps(applied_files, ensure_ascii=False)}")
    return "\n".join(lines)


def background_task_reject_text(payload: dict[str, Any], *, task_id: str) -> str:
    lines = ["background task staged changes rejected", f"task_id={task_id}"]
    status = str(payload.get("status") or "").strip()
    if status:
        lines.append(f"status={status}")
    artifact = dict(payload.get("artifact") or {})
    final_apply_state = str(artifact.get("final_apply_state") or "").strip()
    if final_apply_state:
        lines.append(f"final_apply_state={final_apply_state}")
    summary = str(payload.get("summary") or "").strip()
    if summary:
        lines.append(f"summary={summary}")
    return "\n".join(lines)


def background_task_cancel_text(payload: dict[str, Any], *, task_id: str) -> str:
    action = (
        "background task cancelled"
        if str(payload.get("status") or "").strip() == "cancelled"
        else "background task cancel requested"
    )
    lines = [action, f"task_id={task_id}"]
    for key in ("status", "queue_state", "summary"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    lines.append(f"cancel_requested={'true' if payload.get('cancel_requested') else 'false'}")
    return "\n".join(lines)


def background_task_retry_text(payload: dict[str, Any], *, task_id: str) -> str:
    lines = ["background task retry submitted", f"task_id={task_id}"]
    status = str(payload.get("status") or "").strip()
    if status:
        lines.append(f"status={status}")
    if payload.get("dispatch_id") not in (None, "", 0):
        lines.append(f"dispatch_id={payload['dispatch_id']}")
    if payload.get("retry_count") not in (None, ""):
        lines.append(f"retry_count={payload['retry_count']}")
    summary = str(payload.get("summary") or "").strip()
    if summary:
        lines.append(f"summary={summary}")
    return "\n".join(lines)


def background_teammate_submission_text(
    *,
    handle: Any,
    provider: str,
    model: str,
    reasoning_effort: str,
    allowed_paths: list[str],
    blocked_paths: list[str],
    timeout_seconds: float | None,
    task_text: str,
    preview_text_fn: Callable[..., str],
) -> str:
    detail_pairs: list[tuple[str, Any]] = []
    if provider:
        detail_pairs.append(("provider", provider))
    if model:
        detail_pairs.append(("model", model))
    if reasoning_effort:
        detail_pairs.append(("reasoning_effort", reasoning_effort))
    if allowed_paths:
        detail_pairs.append(("allowed_paths", allowed_paths))
    if blocked_paths:
        detail_pairs.append(("blocked_paths", blocked_paths))
    if timeout_seconds is not None:
        detail_pairs.append(("timeout_seconds", timeout_seconds))
    if str(getattr(handle, "provider", "") or "").strip():
        detail_pairs.append(("queue", handle.provider))
    detail_pairs.append(("task", preview_text_fn(task_text, max_chars=96)))
    return submitted_task_text(title="background teammate submitted", handle=handle, detail_pairs=detail_pairs)
