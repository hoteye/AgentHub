from __future__ import annotations

from cli.agent_cli.background_tasks import adapter_runtime
from cli.agent_cli.background_tasks import lifecycle_runtime


def test_is_terminal_background_task_state_normalizes_terminal_values() -> None:
    assert lifecycle_runtime.is_terminal_background_task_state(" completed ")
    assert lifecycle_runtime.is_terminal_background_task_state("FAILED")
    assert lifecycle_runtime.is_terminal_background_task_state("cancelled")
    assert not lifecycle_runtime.is_terminal_background_task_state("running")


def test_lifecycle_last_event_only_uses_cancel_requested_for_non_terminal_states() -> None:
    assert lifecycle_runtime.lifecycle_last_event(queue_state="running", cancel_requested=True) == "cancel_requested"
    assert lifecycle_runtime.lifecycle_last_event(queue_state="completed", cancel_requested=True) == "dispatch_completed"


def test_resolve_status_text_prefers_terminal_queue_state_when_result_is_not_terminal() -> None:
    assert adapter_runtime.resolve_status_text(result_status="running", queue_state="failed") == "failed"
