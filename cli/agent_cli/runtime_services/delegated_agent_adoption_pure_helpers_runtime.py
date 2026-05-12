from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_NON_ADOPTABLE_TERMINAL_REASONS = {
    "close_requested",
    "orphan_cleanup",
    "restore_resolution_failed",
    "role_override_changed",
}


def delegated_result_adoptable(session: Any) -> bool:
    status = str(session.status or "").strip().lower()
    terminal_reason = str(session.terminal_reason or "").strip().lower()
    if status != "closed":
        return True
    return terminal_reason not in _NON_ADOPTABLE_TERMINAL_REASONS


def runtime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def delegated_session_if_present(runtime: Any, agent_id: str) -> Any | None:
    lock = getattr(runtime, "_delegated_agents_lock", None)
    sessions = getattr(runtime, "_delegated_agents", None)
    normalized_id = str(agent_id or "").strip()
    if not normalized_id or lock is None or sessions is None:
        return None
    with lock:
        return sessions.get(normalized_id)
