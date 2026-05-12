from __future__ import annotations

from typing import Any


def preview_text(value: Any, *, max_chars: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def background_teammate_summary_text(
    *,
    title: str,
    approval_id: str = "",
    task_id: str = "",
    status: str = "",
    task: str = "",
    provider: str = "",
    model: str = "",
    reasoning_effort: str = "",
    cwd: str = "",
    approval_policy: str = "",
    sandbox_mode: str = "",
    allowed_paths: list[str] | None = None,
    blocked_paths: list[str] | None = None,
    timeout_seconds: float | None = None,
    queue_provider: str = "",
    include_approval_commands: bool = False,
) -> str:
    lines = [str(title or "").strip() or "background teammate update"]
    if approval_id:
        lines.append(f"approval_id={approval_id}")
    if task_id:
        lines.append(f"task_id={task_id}")
    if status:
        lines.append(f"status={status}")
    if provider:
        lines.append(f"provider={provider}")
    if model:
        lines.append(f"model={model}")
    if reasoning_effort:
        lines.append(f"reasoning_effort={reasoning_effort}")
    if cwd:
        lines.append(f"cwd={cwd}")
    if approval_policy:
        lines.append(f"approval_policy={approval_policy}")
    if sandbox_mode:
        lines.append(f"sandbox_mode={sandbox_mode}")
    if sandbox_mode == "workspace-write":
        lines.append("staged_run=true")
        lines.append("final_apply_required=true")
    if timeout_seconds is not None:
        lines.append(f"timeout_seconds={timeout_seconds}")
    if allowed_paths:
        lines.append(f"allowed_paths={allowed_paths}")
    if blocked_paths:
        lines.append(f"blocked_paths={blocked_paths}")
    if queue_provider:
        lines.append(f"queue={queue_provider}")
    if task:
        lines.append(f"task={preview_text(task, max_chars=96)}")
    if include_approval_commands and approval_id:
        lines.append(f"/approve {approval_id}")
        lines.append(f"/reject {approval_id}")
        lines.append(f"/reject {approval_id} mode cancel")
    return "\n".join(lines)


def background_teammate_submit_payload(
    *,
    payload: dict[str, Any],
    task_id: str = "",
    status: str = "",
    job_id: str | None = None,
    queue_provider: str | None = None,
    ok: bool,
    error: str | None = None,
) -> dict[str, Any]:
    submit_payload = {
        "ok": ok,
        "task_type": "teammate",
        "task": str(payload.get("task") or "").strip(),
        "provider": str(payload.get("provider") or "").strip() or None,
        "model": str(payload.get("model") or "").strip() or None,
        "reasoning_effort": str(payload.get("reasoning_effort") or "").strip() or None,
        "cwd": str(payload.get("cwd") or "").strip() or None,
        "approval_policy": str(payload.get("approval_policy") or "never").strip() or "never",
        "sandbox_mode": str(payload.get("sandbox_mode") or "read-only").strip() or "read-only",
        "allowed_paths": list(payload.get("allowed_paths") or []),
        "blocked_paths": list(payload.get("blocked_paths") or []),
        "timeout_seconds": payload.get("timeout_seconds"),
    }
    if task_id:
        submit_payload["task_id"] = task_id
    if status:
        submit_payload["status"] = status
    if job_id:
        submit_payload["job_id"] = job_id
    if queue_provider:
        submit_payload["queue_provider"] = queue_provider
    if error:
        submit_payload["error"] = error
    return submit_payload
