from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import threading

import pytest

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_runs.manager import RunManager
from cli.agent_cli.runtime_runs.models import RunStatus
from cli.agent_cli.runtime_services import delegated_agent_adoption_runtime
from cli.agent_cli.runtime_services import delegated_agent_session_runtime
from cli.agent_cli.runtime_services import delegated_agent_turn_runtime


class _CreateRuntime:
    def __init__(self) -> None:
        self.run_manager = RunManager()
        self.thread_id = "thread_main"
        self._delegated_agents_lock = threading.Lock()
        self._delegated_agents: dict[str, object] = {}

    def _delegated_agent_id(self) -> str:
        return "agent_create"

    def _delegated_background_priority(self, **_kwargs):
        return "normal"

    def _delegated_parallel_group(self, *_args, **_kwargs):
        return "read_only"

    def _delegated_planner_input_items(self):
        return []

    def _planner_history(self):
        return []

    def _planner_history_with_context_updates(self, *, planner_history):
        return planner_history

    def _queue_delegated_step(self, _session, *, user_text, source):
        del user_text, source
        return "step_1"

    def _delegated_queue_item(self, message, *, step_id=""):
        return {"message": str(message), "interrupt": False, "step_id": str(step_id)}

    def _refresh_delegated_current_step_id(self, _session):
        return None

    def _notify_delegated_scheduler(self):
        return None

    def _start_delegated_agent_worker(self, _session):
        return None


class _WorkerRuntime:
    def __init__(self, session: SimpleNamespace) -> None:
        self.thread_id = "thread_worker"
        self.run_manager = RunManager()
        self._session = session

    def _delegated_session(self, _agent_id: str):
        return self._session

    def _normalized_delegated_queue_item(self, item):
        return delegated_agent_session_runtime.normalized_delegated_queue_item(item)

    def _wait_for_delegated_slot(self, _session):
        return {"allowed": True}

    def _sync_delegated_background_task(self, _session):
        return None

    def _notify_delegated_scheduler(self):
        return None

    @contextmanager
    def _bound_cancel_event(self, _event):
        yield

    @contextmanager
    def _bound_callback_suppression(self, **_kwargs):
        yield

    def _interrupt_tuple(self):
        return "interrupted", []

    def _update_delegated_step(self, *_args, **_kwargs):
        return None

    def _record_delegated_checkpoint(self, *_args, **_kwargs):
        return None

    def _refresh_delegated_current_step_id(self, _session):
        return None

    def _assistant_text_from_turn_events(self, _turn_events):
        return ""


class _SessionRuntime:
    def __init__(self, session: SimpleNamespace) -> None:
        self.thread_id = "thread_session"
        self.run_manager = RunManager()
        self._session = session

    def _delegated_session(self, _agent_id: str):
        return self._session

    def _refresh_delegated_current_step_id(self, _session):
        return None

    def _record_delegated_checkpoint(self, *_args, **_kwargs):
        return None

    def _delegated_agent_payload(self, session: SimpleNamespace):
        return {
            "agent_id": session.agent_id,
            "status": session.status,
            "terminal_reason": session.terminal_reason,
        }

    def _notify_delegated_scheduler(self):
        return None

    def _sync_delegated_background_task(self, _session):
        return None


class _WaitRuntime:
    def __init__(self, session: SimpleNamespace) -> None:
        self.thread_id = "thread_wait"
        self.run_manager = RunManager()
        self._session = session

    def _delegated_session(self, _agent_id: str):
        return self._session

    def _delegated_result_adoptable(self, _session):
        return True

    def _mark_delegated_result_adopted(self, _session):
        return None

    def _delegated_agent_payload(self, session: SimpleNamespace):
        return {
            "agent_id": session.agent_id,
            "status": session.status,
            "terminal_reason": session.terminal_reason,
        }

    def _sync_delegated_background_task(self, _session):
        return None

    def _delegated_agent_summary_text(self, _session):
        return "summary"


def _worker_session(*, status: str = "queued", protocol_run_id: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        agent_id="agent_worker",
        role="subagent",
        delegation_mode="background",
        protocol_run_id=protocol_run_id,
        protocol_parent_run_id="",
        protocol_thread_id="",
        config=SimpleNamespace(),
        timeout=30,
        source="route",
        seed_input_items=[],
        seed_history=[],
        replay_input_items=[],
        replay_history=[],
        progress_steps=[],
        progress_checkpoints=[],
        current_step_id="",
        queued_inputs=[{"message": "do work", "interrupt": False, "step_id": "step_1"}],
        active_input=None,
        created_at="2026-04-07T00:00:00+00:00",
        updated_at="2026-04-07T00:00:00+00:00",
        status=status,
        last_input_text="",
        assistant_text="",
        error="",
        last_tool_events=[],
        last_item_events=[],
        last_turn_events=[],
        turn_count=0,
        adopted=False,
        adopted_at="",
        last_wait_reason="",
        last_wait_decision="",
        last_wait_at="",
        last_wait_blocked_ms=None,
        last_wait_timed_out=False,
        terminal_reason="",
        close_requested=False,
        closed=False,
        cancel_event=threading.Event(),
        worker=None,
        condition=threading.Condition(),
        scheduler_reason="",
    )


def test_create_delegated_session_syncs_queued_run_record_with_fallback_run_id() -> None:
    runtime = _CreateRuntime()
    resolution = SimpleNamespace(config=SimpleNamespace(), timeout=30, source="route")
    session = delegated_agent_session_runtime.create_delegated_agent_session(
        runtime,
        session_class=SimpleNamespace,
        task_text="run checks",
        role="subagent",
        resolution=resolution,
        metadata={
            "run_id": "run_proto_1",
            "parent_run_id": "run_parent_1",
            "thread_id": "thread_proto_1",
        },
    )
    assert session.protocol_run_id == ""
    record = runtime.run_manager.get("delegated:agent_create")
    assert record is not None
    assert record.status is RunStatus.CREATED
    assert record.parent_run_id == ""
    assert record.thread_id == "thread_main"


def test_worker_syncs_running_to_completed_with_fallback_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _worker_session()
    runtime = _WorkerRuntime(session)

    def _ok_turn(_runtime, _session, *, user_text: str):
        del user_text
        return CommandExecutionResult(assistant_text="done")

    monkeypatch.setattr(delegated_agent_turn_runtime, "run_delegated_agent_turn", _ok_turn)
    delegated_agent_turn_runtime.run_delegated_agent_worker(runtime, session.agent_id)

    record = runtime.run_manager.get("delegated:agent_worker")
    assert record is not None
    assert record.status is RunStatus.COMPLETED
    assert record.started_at != ""
    assert record.thread_id == "thread_worker"


def test_worker_syncs_failed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _worker_session()
    runtime = _WorkerRuntime(session)

    def _failed_turn(_runtime, _session, *, user_text: str):
        del user_text
        raise RuntimeError("boom")

    monkeypatch.setattr(delegated_agent_turn_runtime, "run_delegated_agent_turn", _failed_turn)
    delegated_agent_turn_runtime.run_delegated_agent_worker(runtime, session.agent_id)

    record = runtime.run_manager.get("delegated:agent_worker")
    assert record is not None
    assert record.status is RunStatus.FAILED


def test_close_agent_result_syncs_cancelled_status() -> None:
    session = SimpleNamespace(
        agent_id="agent_close",
        role="subagent",
        delegation_mode="background",
        protocol_run_id="run_close_1",
        protocol_parent_run_id="",
        protocol_thread_id="",
        worker=None,
        close_requested=False,
        terminal_reason="",
        queued_inputs=[],
        active_input=None,
        closed=False,
        status="queued",
        scheduler_reason="",
        current_step_id="",
        updated_at="",
        cancel_event=threading.Event(),
        condition=threading.Condition(),
    )
    runtime = _SessionRuntime(session)
    delegated_agent_session_runtime.close_agent_result(runtime, session.agent_id)

    record = runtime.run_manager.get("run_close_1")
    assert record is not None
    assert record.status is RunStatus.CANCELLED


def test_wait_agent_result_syncs_completed_and_failed_statuses() -> None:
    completed = SimpleNamespace(
        agent_id="agent_wait_done",
        role="subagent",
        delegation_mode="background",
        protocol_run_id="run_wait_done",
        protocol_parent_run_id="",
        protocol_thread_id="",
        status="completed",
        terminal_reason="completed",
        active_input=None,
        queued_inputs=[],
        adopted=True,
        last_wait_reason="",
        last_wait_decision="",
        last_wait_at="",
        last_wait_blocked_ms=0,
        last_wait_timed_out=False,
        updated_at="",
        condition=threading.Condition(),
    )
    runtime_done = _WaitRuntime(completed)
    delegated_agent_adoption_runtime.wait_agent_result(runtime_done, completed.agent_id)
    done_record = runtime_done.run_manager.get("run_wait_done")
    assert done_record is not None
    assert done_record.status is RunStatus.COMPLETED

    failed = SimpleNamespace(
        agent_id="agent_wait_fail",
        role="subagent",
        delegation_mode="background",
        protocol_run_id="run_wait_fail",
        protocol_parent_run_id="",
        protocol_thread_id="",
        status="failed",
        terminal_reason="failed",
        active_input=None,
        queued_inputs=[],
        adopted=False,
        last_wait_reason="",
        last_wait_decision="",
        last_wait_at="",
        last_wait_blocked_ms=0,
        last_wait_timed_out=False,
        updated_at="",
        condition=threading.Condition(),
    )
    runtime_fail = _WaitRuntime(failed)
    delegated_agent_adoption_runtime.wait_agent_result(runtime_fail, failed.agent_id)
    failed_record = runtime_fail.run_manager.get("run_wait_fail")
    assert failed_record is not None
    assert failed_record.status is RunStatus.FAILED
