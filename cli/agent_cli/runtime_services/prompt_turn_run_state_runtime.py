from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.runtime_runs import RunKind, RunStatus


def preview_text(value: Any, *, max_chars: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def turn_run_id(run_token: str) -> str:
    return f"turn:{str(run_token or '').strip()}"


def turn_run_manager(runtime: Any) -> Any | None:
    return getattr(runtime, "run_manager", None)


def safe_turn_run_create(
    runtime: Any,
    *,
    run_id: str,
    text: str,
) -> None:
    manager = turn_run_manager(runtime)
    if manager is None:
        return
    try:
        manager.create(
            run_id=run_id,
            kind=RunKind.TURN,
            thread_id=str(getattr(runtime, "thread_id", "") or ""),
            summary=preview_text(text) or "turn started",
            payload={
                "thread_id": str(getattr(runtime, "thread_id", "") or ""),
                "cwd": str(getattr(runtime, "cwd", "") or ""),
                "user_text": str(text or "").strip(),
            },
        )
    except Exception:
        return


def safe_turn_run_update(
    runtime: Any,
    run_id: str,
    *,
    status: RunStatus | str | None = None,
    summary: str | None = None,
    payload: Dict[str, Any] | None = None,
) -> None:
    manager = turn_run_manager(runtime)
    if manager is None:
        return
    try:
        manager.update(
            run_id,
            status=status,
            summary=summary,
            payload=payload,
        )
    except Exception:
        return


def safe_turn_run_finish(
    runtime: Any,
    run_id: str,
    *,
    failed: bool = False,
    timed_out: bool = False,
    summary: str | None = None,
    payload: Dict[str, Any] | None = None,
) -> None:
    manager = turn_run_manager(runtime)
    if manager is None:
        return
    try:
        manager.finish(
            run_id,
            failed=failed,
            timed_out=timed_out,
            summary=summary,
            payload=payload,
        )
    except Exception:
        return


def turn_cancelled(state: Dict[str, Any]) -> bool:
    for event in list(state.get("events") or []):
        name = str(getattr(event, "name", "") or "").strip().lower()
        if name == "interrupted":
            return True
        payload = dict(getattr(event, "payload", {}) or {})
        if str(payload.get("reason") or "").strip().lower() == "user_interrupt":
            return True
    return False


def payload_indicates_timeout(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if bool(payload.get("wait_timed_out")) or bool(payload.get("timeout_hit")):
        return True
    if str(payload.get("delegation_outcome") or payload.get("orchestration_outcome") or "").strip().lower() == "timed_out":
        return True
    for value in payload.values():
        if isinstance(value, dict) and payload_indicates_timeout(value):
            return True
    return False


def turn_timed_out(state: Dict[str, Any]) -> bool:
    if payload_indicates_timeout(state.get("protocol_diagnostics")):
        return True
    for event in list(state.get("events") or []):
        name = str(getattr(event, "name", "") or "").strip().lower()
        if name in {"timed_out", "timeout"}:
            return True
        payload = dict(getattr(event, "payload", {}) or {})
        if bool(payload.get("wait_timed_out")) or bool(payload.get("timeout_hit")):
            return True
    return False
