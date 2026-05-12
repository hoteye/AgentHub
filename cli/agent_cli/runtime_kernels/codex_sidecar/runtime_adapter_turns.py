from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.errors import (
    CodexSidecarProcessError,
    CodexSidecarRequestError,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper import CodexSidecarTurnEventMapper


class CodexSidecarRuntimeTurnMixin:
    def _collect_turn_events(
        self,
        *,
        turn_id: str,
        mapper: CodexSidecarTurnEventMapper,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        started_event = mapper.synthesize_turn_started(thread_id=self.thread_id, turn_id=turn_id)
        if started_event is not None:
            self._append_turn_event(events, started_event)

        def matches_notification(notification: Any) -> bool:
            return _notification_matches_turn(
                notification.params,
                thread_id=self.thread_id,
                turn_id=turn_id,
                method=notification.method,
            )

        while not mapper.terminal_seen:
            try:
                notification = self.kernel.client.get_notification_matching(
                    matches_notification,
                    timeout=0.25,
                )
            except (CodexSidecarProcessError, CodexSidecarRequestError) as exc:
                self._append_turn_event(
                    events,
                    {
                        "type": "turn.failed",
                        "thread_id": self.thread_id,
                        "turn_id": turn_id,
                        "error": {"message": str(exc)},
                    },
                )
                break
            self._drain_server_requests_for_turn(
                mapper=mapper,
                thread_id=self.thread_id,
                turn_id=turn_id,
            )
            if notification is None:
                proc = getattr(self.kernel.client.supervisor, "process", None)
                if proc is not None and proc.poll() is not None:
                    message = (
                        "codex sidecar exited before turn completion: "
                        f"code={proc.returncode}, "
                        f"stderr={self.kernel.client.supervisor.stderr_tail()}"
                    )
                    self._append_turn_event(
                        events,
                        {
                            "type": "turn.failed",
                            "thread_id": self.thread_id,
                            "turn_id": turn_id,
                            "error": {"message": message},
                        },
                    )
                    break
                continue
            for event in mapper.map_notification(notification):
                self._append_turn_event(events, event)
                if str(event.get("type") or "") in {
                    "turn.completed",
                    "turn.failed",
                    "turn.interrupted",
                }:
                    self._mark_active_turn_status(turn_id, str(event.get("type") or ""))
        if not any(
            isinstance(event, dict)
            and str(event.get("type") or "").strip()
            in {"turn.completed", "turn.failed", "turn.interrupted"}
            for event in events
        ):
            self._append_turn_event(
                events,
                {
                    "type": "turn.failed",
                    "thread_id": self.thread_id,
                    "turn_id": turn_id,
                    "error": {"message": "codex sidecar turn ended without terminal event"},
                },
            )
        return events

    def _mark_active_turn_started(self, turn_id: str) -> None:
        import time

        with self._active_turn_lock:
            self._active_turn_id = str(turn_id or "").strip()
            self._active_turn_started_at = time.monotonic()
            self._active_turn_status = "running"
            self._active_turn_interrupt_requested = False

    def _mark_active_turn_status(self, turn_id: str, status: str) -> None:
        with self._active_turn_lock:
            if self._active_turn_id == str(turn_id or "").strip():
                self._active_turn_status = str(status or "").strip()

    def _clear_active_turn(self, turn_id: str) -> None:
        with self._active_turn_lock:
            if self._active_turn_id != str(turn_id or "").strip():
                return
            self._active_turn_id = ""
            self._active_turn_started_at = 0.0
            self._active_turn_status = ""
            self._active_turn_interrupt_requested = False

    def _active_turn_snapshot(self) -> tuple[str, str, bool]:
        with self._active_turn_lock:
            return (
                self._active_turn_id,
                self._active_turn_status,
                self._active_turn_interrupt_requested,
            )

    def _append_turn_event(self, events: list[dict[str, Any]], event: dict[str, Any]) -> None:
        normalized = dict(event)
        events.append(normalized)
        callback = self.turn_event_callback
        if callable(callback):
            try:
                callback(normalized)
            except Exception:
                pass


def _notification_matches_turn(
    params: dict[str, Any],
    *,
    thread_id: str,
    turn_id: str,
    method: str,
) -> bool:
    if method == "error" or method.startswith("$agenthub/"):
        return True
    raw_thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
    if raw_thread_id and raw_thread_id != thread_id:
        return False
    raw_turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
    turn = params.get("turn")
    if isinstance(turn, dict):
        raw_turn_id = (
            raw_turn_id
            or str(turn.get("id") or turn.get("turnId") or turn.get("turn_id") or "").strip()
        )
    if raw_turn_id and turn_id and raw_turn_id != turn_id:
        return False
    if method in {"thread/status/changed", "thread/tokenUsage/updated"}:
        return True
    return bool(raw_thread_id or raw_turn_id)
