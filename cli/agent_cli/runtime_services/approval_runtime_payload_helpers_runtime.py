from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import ToolEvent


def approval_failure_event(*, name: str, summary: str, error: str) -> ToolEvent:
    return ToolEvent(
        name=name,
        ok=False,
        summary=summary,
        payload={"ok": False, "error": error},
    )


def patch_approval_payload(
    *,
    approval_ticket: Any,
    preview: Dict[str, Any],
    approval_reason: str,
    available_decisions: list[dict[str, Any]],
    session_contract: Dict[str, Any],
    action_policy_payload: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "approval_id": approval_ticket.approval_id if approval_ticket is not None else None,
        "status": approval_ticket.status if approval_ticket is not None else "pending",
        "summary": approval_ticket.summary if approval_ticket is not None else "Approve workspace patch",
        "reason": approval_ticket.reason if approval_ticket is not None else approval_reason,
        "available_decisions": (
            list(getattr(approval_ticket, "available_decisions", []) or [])
            if approval_ticket is not None
            else available_decisions
        ),
        "session_cache_keys": (
            list(getattr(approval_ticket, "session_cache_keys", []) or [])
            if approval_ticket is not None
            else list(session_contract.get("session_cache_keys") or [])
        ),
        "grant_root": (
            str(getattr(approval_ticket, "grant_root", "") or "").strip() or None
            if approval_ticket is not None
            else str(session_contract.get("grant_root") or "").strip() or None
        ),
        **preview,
    }
    if action_policy_payload:
        payload["action_policy"] = action_policy_payload
    return payload


def patch_approval_event(payload: Dict[str, Any]) -> ToolEvent:
    return ToolEvent(
        name="patch_approval_requested",
        ok=True,
        summary=f"patch approval requested {payload['approval_id']}",
        payload=payload,
    )


def shell_approval_summary(exec_mode: str) -> str:
    return "Approve shell session start" if exec_mode == "session_start" else "Approve shell command"


def shell_approval_metadata(
    *,
    exec_mode: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    metadata: Dict[str, Any] | None,
    sandbox_permissions: str | None,
    justification: str | None,
    prefix_rule: list[str] | None,
    additional_permissions: Dict[str, Any] | None,
    action_policy_payload: Dict[str, Any],
) -> Dict[str, Any]:
    approval_metadata = {
        "source": "cli_shell_start" if exec_mode == "session_start" else "cli_shell",
        "exec_mode": exec_mode,
        "cwd": cwd,
        "login": bool(login),
        "tty": bool(tty),
        "shell": shell,
        "max_output_chars": int(max_output_chars),
        **dict(metadata or {}),
    }
    if sandbox_permissions:
        approval_metadata["sandbox_permissions"] = sandbox_permissions
    if justification:
        approval_metadata["justification"] = justification
    if prefix_rule is not None:
        approval_metadata["prefix_rule"] = list(prefix_rule)
    if additional_permissions is not None:
        approval_metadata["additional_permissions"] = dict(additional_permissions)
    if action_policy_payload:
        approval_metadata["action_policy"] = action_policy_payload
    return approval_metadata


def shell_request_payload(
    *,
    command: str,
    timeout_sec: int,
    exec_mode: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    sandbox_permissions: str | None,
    justification: str | None,
    prefix_rule: list[str] | None,
    additional_permissions: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return {
        "command": command,
        "timeout_sec": int(timeout_sec),
        "exec_mode": exec_mode,
        "cwd": cwd,
        "login": bool(login),
        "tty": bool(tty),
        "shell": shell,
        "max_output_chars": int(max_output_chars),
        "sandbox_permissions": sandbox_permissions,
        "justification": justification,
        "prefix_rule": list(prefix_rule) if prefix_rule is not None else None,
        "additional_permissions": (
            dict(additional_permissions) if additional_permissions is not None else None
        ),
    }


def shell_approval_payload(
    *,
    approval_ticket: Any,
    approval_reason: str,
    command: str,
    timeout_sec: int,
    exec_mode: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    sandbox_permissions: str | None,
    justification: str | None,
    prefix_rule: list[str] | None,
    additional_permissions: Dict[str, Any] | None,
    action_policy_payload: Dict[str, Any],
    available_decisions: list[dict[str, Any]],
    session_cache_keys: list[str],
    proposed_rule: Dict[str, Any] | None,
    resolved_policy_payload: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "approval_id": approval_ticket.approval_id if approval_ticket is not None else None,
        "status": approval_ticket.status if approval_ticket is not None else "pending",
        "summary": (
            approval_ticket.summary
            if approval_ticket is not None
            else shell_approval_summary(exec_mode)
        ),
        "reason": approval_ticket.reason if approval_ticket is not None else approval_reason,
        **shell_request_payload(
            command=command,
            timeout_sec=timeout_sec,
            exec_mode=exec_mode,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            sandbox_permissions=sandbox_permissions,
            justification=justification,
            prefix_rule=prefix_rule,
            additional_permissions=additional_permissions,
        ),
        "action_policy": action_policy_payload or None,
        "available_decisions": (
            list(getattr(approval_ticket, "available_decisions", []) or [])
            if approval_ticket is not None
            else available_decisions
        ),
        "session_cache_keys": (
            list(getattr(approval_ticket, "session_cache_keys", []) or [])
            if approval_ticket is not None
            else session_cache_keys
        ),
        "proposed_rule": (
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if approval_ticket is not None and isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else proposed_rule
        ),
    }
    if resolved_policy_payload:
        payload = {**dict(resolved_policy_payload), **payload}
    return payload


def shell_approval_event(payload: Dict[str, Any]) -> ToolEvent:
    return ToolEvent(
        name="shell_approval_requested",
        ok=True,
        summary=f"shell approval requested {payload['approval_id']}",
        payload=payload,
    )


def background_teammate_request_payload(
    *,
    task: str,
    provider: str,
    model: str,
    reasoning_effort: str,
    task_cwd: str,
    queue_cwd: str,
    approval_policy: str,
    sandbox_mode: str,
    allowed_paths: list[str],
    blocked_paths: list[str],
    timeout_seconds: float | None,
) -> Dict[str, Any]:
    return {
        "task": task,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "cwd": task_cwd,
        "queue_cwd": queue_cwd,
        "approval_policy": approval_policy,
        "sandbox_mode": sandbox_mode,
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "timeout_seconds": timeout_seconds,
    }


def background_teammate_metadata(**request_payload: Any) -> Dict[str, Any]:
    return {
        "source": "cli_background_teammate",
        "provider_name": request_payload.get("provider"),
        "model": request_payload.get("model"),
        "reasoning_effort": request_payload.get("reasoning_effort"),
        "cwd": request_payload.get("cwd"),
        "queue_cwd": request_payload.get("queue_cwd"),
        "approval_policy": request_payload.get("approval_policy"),
        "sandbox_mode": request_payload.get("sandbox_mode"),
        "allowed_paths": request_payload.get("allowed_paths"),
        "blocked_paths": request_payload.get("blocked_paths"),
        "timeout_seconds": request_payload.get("timeout_seconds"),
    }


def background_teammate_approval_payload(
    *,
    approval_ticket: Any,
    approval_reason: str,
    request_payload: Dict[str, Any],
    fallback_available_decisions_factory: Callable[[], list[dict[str, Any]]],
    summary_text_factory: Callable[..., str],
) -> Dict[str, Any]:
    approval_id = approval_ticket.approval_id if approval_ticket is not None else None
    status = approval_ticket.status if approval_ticket is not None else "pending"
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": status,
        "summary": (
            approval_ticket.summary
            if approval_ticket is not None
            else "Approve background teammate live workspace run"
        ),
        "reason": approval_ticket.reason if approval_ticket is not None else approval_reason,
        "task_type": "teammate",
        "task": request_payload["task"],
        "provider": request_payload["provider"],
        "model": request_payload["model"],
        "reasoning_effort": request_payload["reasoning_effort"],
        "cwd": request_payload["cwd"],
        "queue_cwd": request_payload["queue_cwd"],
        "approval_policy": request_payload["approval_policy"],
        "sandbox_mode": request_payload["sandbox_mode"],
        "allowed_paths": request_payload["allowed_paths"],
        "blocked_paths": request_payload["blocked_paths"],
        "timeout_seconds": request_payload["timeout_seconds"],
        "available_decisions": (
            list(getattr(approval_ticket, "available_decisions", []) or [])
            if approval_ticket is not None
            else fallback_available_decisions_factory()
        ),
        "summary_text": summary_text_factory(
            title="background teammate approval requested",
            approval_id=str(approval_id or "").strip(),
            status=status,
            task=request_payload["task"],
            provider=request_payload["provider"],
            model=request_payload["model"],
            reasoning_effort=request_payload["reasoning_effort"],
            cwd=request_payload["cwd"],
            approval_policy=request_payload["approval_policy"],
            sandbox_mode=request_payload["sandbox_mode"],
            allowed_paths=request_payload["allowed_paths"],
            blocked_paths=request_payload["blocked_paths"],
            timeout_seconds=request_payload["timeout_seconds"],
            include_approval_commands=True,
        ),
    }


def background_teammate_approval_event(payload: Dict[str, Any]) -> ToolEvent:
    return ToolEvent(
        name="background_teammate_approval_requested",
        ok=True,
        summary=f"background teammate approval requested {payload['approval_id']}",
        payload=payload,
    )
