from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_services import delegated_agent_background_state_transition_runtime


def test_background_status_and_notification_map_orphaned_closed_session() -> None:
    status = delegated_agent_background_state_transition_runtime.delegated_background_task_status(
        "closed",
        has_text=False,
        terminal_reason="orphan_cleanup",
    )
    notification = delegated_agent_background_state_transition_runtime.delegated_background_notification_state(
        status="closed",
        adopted=False,
        terminal_reason="orphan_cleanup",
    )

    assert status == "cancelled"
    assert notification == "orphaned"


def test_request_session_cleanup_closes_idle_session_and_records_checkpoint() -> None:
    recorded: dict[str, object] = {}
    session = SimpleNamespace(
        closed=False,
        terminal_reason="",
        worker=None,
        active_input=None,
        cancel_event=SimpleNamespace(set=lambda: recorded.setdefault("cancelled", True)),
        close_requested=False,
        queued_inputs=[{"message": "hello"}],
        status="queued",
        scheduler_reason="busy",
        current_step_id="step_1",
        updated_at="",
    )

    outcome = delegated_agent_background_state_transition_runtime.request_session_cleanup(
        session=session,
        reason="orphan_cleanup",
        summary="cleanup requested",
        now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
        refresh_current_step_id_fn=lambda current: recorded.setdefault("refreshed", current.current_step_id),
        record_checkpoint_fn=lambda *args, **kwargs: recorded.setdefault("checkpoint", kwargs),
    )

    assert outcome == {"changed": True, "worker_running": False}
    assert session.closed is True
    assert session.close_requested is True
    assert session.status == "closed"
    assert session.active_input is None
    assert session.queued_inputs == []
    assert session.scheduler_reason == ""
    assert session.terminal_reason == "orphan_cleanup"
    assert session.updated_at == "2026-04-05T00:00:00+00:00"
    assert recorded["checkpoint"] == {
        "kind": "session_orphan_cleanup",
        "status": "closed",
        "summary": "cleanup requested",
        "step_id": "step_1",
    }
