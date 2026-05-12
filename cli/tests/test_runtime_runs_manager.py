from cli.agent_cli.runtime_runs.manager import RunManager
from cli.agent_cli.runtime_runs.models import RunKind, RunStatus


def test_run_manager_create_running_completed_and_filters() -> None:
    manager = RunManager()
    created = manager.create(
        run_id="run_1",
        kind=RunKind.TURN,
        thread_id="thread_a",
        parent_run_id="parent_1",
        summary="created",
        payload={"step": 1},
    )
    assert created.status is RunStatus.CREATED

    running = manager.update("run_1", status=RunStatus.RUNNING, summary="running")
    assert running.status is RunStatus.RUNNING
    assert running.started_at != ""

    completed = manager.finish("run_1", summary="done")
    assert completed.status is RunStatus.COMPLETED
    assert completed.finished_at != ""
    assert completed.summary == "done"

    assert [item.run_id for item in manager.list(run_id="run_1")] == ["run_1"]
    assert [item.run_id for item in manager.list(thread_id="thread_a")] == ["run_1"]
    assert [item.run_id for item in manager.list(parent_run_id="parent_1")] == ["run_1"]
    assert [item.run_id for item in manager.list(status=RunStatus.COMPLETED)] == ["run_1"]


def test_run_manager_create_cancelled() -> None:
    manager = RunManager()
    manager.create(
        run_id="run_2",
        kind="workflow",
        thread_id="thread_b",
        parent_run_id="parent_2",
    )
    cancelled = manager.cancel("run_2")
    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.cancelled_at != ""
    assert cancelled.finished_at != ""
    assert cancelled.summary == "cancelled"


def test_run_manager_timeout_exposes_terminal_projection_fields() -> None:
    manager = RunManager()
    manager.create(run_id="run_3", kind="turn", thread_id="thread_c")
    manager.update("run_3", status=RunStatus.RUNNING, summary="running")

    timed_out = manager.timeout("run_3")

    assert timed_out.status is RunStatus.TIMED_OUT
    assert timed_out.finished_at != ""
    assert timed_out.timed_out_at != ""
    assert timed_out.is_terminal is True
    assert timed_out.terminal_state == "timed_out"
    assert timed_out.to_dict()["terminal_state"] == "timed_out"
