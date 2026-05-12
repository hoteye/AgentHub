from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import shell_session_runtime


class ShellCompletedSessionCache:
    def __init__(
        self,
        *,
        lock: threading.Lock,
        completed_sessions: Dict[str, Dict[str, Any]],
        completed_session_order: List[str],
        completed_cache_limit: int,
    ) -> None:
        self._lock = lock
        self._completed_sessions = completed_sessions
        self._completed_session_order = completed_session_order
        self._completed_cache_limit = completed_cache_limit

    def get_completed_payload(self, session_id: str) -> Dict[str, Any] | None:
        normalized_session_id = str(session_id or "").strip()
        with self._lock:
            payload = self._completed_sessions.get(normalized_session_id)
        if payload is None:
            return None
        cloned = dict(payload)
        history = cloned.get("_event_history")
        if isinstance(history, list):
            cloned["_event_history"] = [dict(item) for item in history if isinstance(item, dict)]
        return cloned

    @staticmethod
    def completed_replay_event(completed_payload: Dict[str, Any]) -> ToolEvent:
        return shell_session_runtime.completed_replay_event(completed_payload)

    @staticmethod
    def subscribe_payload_from_completed_payload(completed_payload: Dict[str, Any]) -> Dict[str, Any]:
        return shell_session_runtime.subscribe_payload_from_completed_payload(completed_payload)

    @staticmethod
    def replayable_event_history(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return shell_session_runtime.replayable_event_history(payloads)

    @staticmethod
    def completed_event_history(completed_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return shell_session_runtime.completed_event_history(completed_payload)

    @staticmethod
    def completed_readonly_write_payload(
        completed_payload: Dict[str, Any],
        *,
        input_chars: str,
    ) -> Dict[str, Any]:
        return shell_session_runtime.completed_readonly_write_payload(
            completed_payload,
            input_chars=input_chars,
        )

    def record_completed_payload(
        self,
        session_id: str,
        payload: Dict[str, Any],
        *,
        event_history: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        payload_copy = dict(payload)
        if event_history:
            payload_copy["_event_history"] = shell_session_runtime.replayable_event_history(event_history)
        with self._lock:
            self._completed_sessions[normalized_session_id] = payload_copy
            if normalized_session_id in self._completed_session_order:
                self._completed_session_order.remove(normalized_session_id)
            self._completed_session_order.append(normalized_session_id)
            while len(self._completed_session_order) > self._completed_cache_limit:
                evicted_session_id = self._completed_session_order.pop(0)
                self._completed_sessions.pop(evicted_session_id, None)
