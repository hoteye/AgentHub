from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def workspace_root_for_runtime(runtime: Any) -> Path:
    return Path(str(getattr(runtime, "cwd", None) or Path.cwd())).resolve()


def initial_status_data(
    *,
    runtime: Any,
    session_started_text: str,
    thread_id: Any,
    thread_name: Any,
) -> dict[str, str]:
    return {
        "session_started": session_started_text,
        "prompt_count": "0",
        "last_input": "-",
        "last_tool": "-",
        "last_ok": "-",
        "last_summary": "-",
        "thread_id": thread_id or "-",
        "thread_name": thread_name or "-",
        **(getattr(runtime, "runtime_policy_status", lambda: {})() or {}),
        **(getattr(runtime, "approval_status", lambda: {})() or {}),
        **runtime.agent.provider_status(),
    }


def subtitle_text(t: Callable[[str], str], *, busy: bool) -> str:
    base = t("app.subtitle.base")
    state = t("app.subtitle.running" if busy else "app.subtitle.ready")
    return f"{base} | {state}"


def runtime_has_active_run(runtime: Any) -> bool:
    has_active_run = getattr(runtime, "has_active_run", None)
    if not callable(has_active_run):
        return False
    try:
        return bool(has_active_run())
    except Exception:
        return False


def has_interruptible_run(*, busy: bool, runtime: Any) -> bool:
    return busy or runtime_has_active_run(runtime)


def has_pending_runtime_work(*, busy: bool, runtime: Any, queue_size: int) -> bool:
    return has_interruptible_run(busy=busy, runtime=runtime) or queue_size > 0


def notice_key_for_pending(*, has_pending_work: bool, queued_key: str, running_key: str) -> str:
    return queued_key if has_pending_work else running_key


def stop_optional_timer(timer: Any) -> None:
    if timer is None:
        return
    try:
        timer.stop()
    except Exception:
        pass

