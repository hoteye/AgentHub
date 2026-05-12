from __future__ import annotations

from collections import deque
from types import SimpleNamespace

from cli.agent_cli.ui.status_controller import StatusControllerMixin


class _StatusProbe(StatusControllerMixin):
    def __init__(self) -> None:
        self.status_data: dict[str, str] = {}
        self._busy_status_label = ""
        self._busy = False
        self._busy_started_at = None
        self._busy_status_hidden = False
        self._pending_status_indicator_restore = False
        self._assistant_message_streaming_active = False
        self._queued_run_labels: deque[str] = deque()
        self._subtitle_calls: list[bool] = []
        self._update_calls = 0
        self._refresh_calls = 0
        self.sub_title = ""

    def _refresh_dynamic_hint(self) -> None:
        self._refresh_calls += 1

    def _subtitle_text(self, busy: bool) -> str:
        self._subtitle_calls.append(busy)
        return "busy" if busy else "idle"

    def _busy_label_for_queued_request(self, text: str) -> str:
        return text or "working"

    def _update_status(self, status: dict[str, str]) -> None:
        self.status_data.update({str(k): str(v) for k, v in status.items()})
        self._update_calls += 1


def test_set_request_user_input_waiting_true_sets_flag_and_label() -> None:
    probe = _StatusProbe()

    probe._set_request_user_input_waiting(True)

    assert probe.status_data["request_user_input_waiting"] == "true"
    assert probe._busy_status_label == "waiting for user input"
    assert probe._refresh_calls == 1


def test_set_request_user_input_waiting_false_clears_waiting_label() -> None:
    probe = _StatusProbe()
    probe._busy_status_label = "waiting for user input"

    probe._set_request_user_input_waiting(False)

    assert probe.status_data["request_user_input_waiting"] == "false"
    assert probe._busy_status_label == ""
    assert probe._refresh_calls == 1


def test_set_busy_false_clears_waiting_flag_after_busy_run() -> None:
    probe = _StatusProbe()
    probe._set_request_user_input_waiting(True)
    probe._set_busy(True)

    probe._set_busy(False)

    assert probe.status_data["request_user_input_waiting"] == "false"
    assert probe.status_data["busy"] == "false"
    assert probe._busy_status_label == ""
    assert probe.sub_title == "idle"


def test_pending_approval_count_keeps_status_only_value_without_runtime_ticket() -> None:
    probe = _StatusProbe()
    probe.status_data.update(
        {
            "pending_approvals": "1",
            "latest_pending_approval_id": "approval_status_only",
        }
    )

    assert probe._pending_approval_count() == 1


def test_pending_approval_count_ignores_stale_status_after_ticket_decision() -> None:
    class _Store:
        @staticmethod
        def get_approval_ticket(approval_id: str):
            assert approval_id == "approval_done"
            return SimpleNamespace(status="approved")

    probe = _StatusProbe()
    probe.runtime = SimpleNamespace(
        gateway_state_store=_Store(),
        list_approval_tickets=lambda limit=20, status="pending": [],
    )
    probe.status_data.update(
        {
            "pending_approvals": "1",
            "latest_pending_approval_id": "approval_done",
        }
    )

    assert probe._pending_approval_count() == 0
