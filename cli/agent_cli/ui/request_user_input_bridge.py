from __future__ import annotations

from dataclasses import dataclass, field
import threading
import uuid
from typing import Any, Callable

from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
    normalize_request_user_input_response,
)


@dataclass
class PendingRequestUserInput:
    request_id: str
    questions: list[dict[str, Any]]
    response_event: threading.Event = field(default_factory=threading.Event)
    response_payload: dict[str, Any] | None = None
    cancelled: bool = False

    @property
    def question_ids(self) -> set[str]:
        return {
            str(item.get("id") or "").strip()
            for item in list(self.questions or [])
            if isinstance(item, dict)
        }


class RequestUserInputBridge:
    def __init__(
        self,
        *,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingRequestUserInput] = {}
        self._request_id_factory = request_id_factory or (lambda: f"rui_{uuid.uuid4().hex}")

    def start_request(self, payload: dict[str, Any]) -> PendingRequestUserInput:
        questions = normalize_request_user_input_questions((payload or {}).get("questions"))
        pending = PendingRequestUserInput(
            request_id=str(self._request_id_factory()).strip() or f"rui_{uuid.uuid4().hex}",
            questions=questions,
        )
        with self._lock:
            self._pending[pending.request_id] = pending
        return pending

    def snapshot(self) -> list[PendingRequestUserInput]:
        with self._lock:
            return list(self._pending.values())

    def pending_request(self, request_id: str) -> PendingRequestUserInput | None:
        with self._lock:
            return self._pending.get(str(request_id or "").strip())

    def resolve_request(self, request_id: str, response_payload: dict[str, Any] | None) -> bool:
        request_key = str(request_id or "").strip()
        with self._lock:
            pending = self._pending.get(request_key)
        if pending is None:
            return False
        pending.response_payload = normalize_request_user_input_response(
            dict(response_payload or {}),
            question_ids=pending.question_ids,
        )
        pending.cancelled = False
        pending.response_event.set()
        return True

    def cancel_request(self, request_id: str) -> bool:
        request_key = str(request_id or "").strip()
        with self._lock:
            pending = self._pending.get(request_key)
        if pending is None:
            return False
        pending.cancelled = True
        pending.response_payload = None
        pending.response_event.set()
        return True

    def cancel_all(self) -> int:
        with self._lock:
            pending_requests = list(self._pending.values())
        for pending in pending_requests:
            pending.cancelled = True
            pending.response_payload = None
            pending.response_event.set()
        return len(pending_requests)

    def finish_request(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(str(request_id or "").strip(), None)

    def wait_for_response(
        self,
        request_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        request_key = str(request_id or "").strip()
        with self._lock:
            pending = self._pending.get(request_key)
        if pending is None:
            return None
        resolved = pending.response_event.wait(timeout_seconds)
        if not resolved or pending.cancelled:
            return None
        if not isinstance(pending.response_payload, dict):
            return None
        return dict(pending.response_payload)

    def build_handler(
        self,
        *,
        on_request: Callable[[PendingRequestUserInput], Any],
        timeout_seconds: float | None = None,
    ) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
        def handler(payload: dict[str, Any]) -> dict[str, Any] | None:
            pending = self.start_request(payload)
            try:
                on_request(pending)
            except Exception:
                self.cancel_request(pending.request_id)
            try:
                return self.wait_for_response(
                    pending.request_id,
                    timeout_seconds=timeout_seconds,
                )
            finally:
                self.finish_request(pending.request_id)

        return handler
