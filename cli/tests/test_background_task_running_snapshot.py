from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.background_tasks import tasks_execution_runtime, tasks_stream_runtime, tasks_support_runtime, tasks_teammate_runtime
from cli.agent_cli.background_tasks.models import BackgroundTaskStatus, BackgroundTaskType, TaskEnvelope
from cli.agent_cli.background_tasks.storage import BackgroundTaskStorage
from cli.agent_cli.background_tasks.subprocess_runtime import SubprocessRunResult


def test_running_snapshot_is_written_and_updated_from_stream_events(tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_running_snapshot",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={"task": "inspect repo"},
    )
    storage.upsert_envelope(envelope, queue_state="running", runner_pid=4321, runner_token="runner-token")

    state = tasks_teammate_runtime.new_headless_jsonl_state()
    stream_progress: dict[str, object] = {"last_persist_monotonic": 0.0}
    monotonic_values = iter([1.0, 2.0])

    def _monotonic() -> float:
        return float(next(monotonic_values))

    def _task_artifact(
        envelope_arg: TaskEnvelope,
        *,
        queue_state: str,
        cancel_requested: bool,
        extra: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_id": envelope_arg.task_id,
            "queue_state": queue_state,
            "cancel_requested": cancel_requested,
        }
        payload.update(dict(extra))
        return payload

    for text in ("running pass #1", "running pass #2"):
        line = json.dumps(
            {
                "type": "item.updated",
                "item": {"id": "msg_1", "type": "agent_message", "phase": "commentary", "text": text},
            },
            ensure_ascii=False,
        )
        tasks_stream_runtime.consume_teammate_stdout_line(
            line,
            state=state,
            storage=storage,
            envelope=envelope,
            started_at="2026-04-05T10:00:00+00:00",
            retry_count=0,
            live_cwd=tmp_path,
            provider="openai",
            model="gpt_54",
            reasoning_effort="high",
            allowed_paths=[],
            blocked_paths=[],
            staged_workspace=False,
            bootstrap_artifact={"bootstrap_diagnostics": {"cwd_exists": True}},
            stream_progress=stream_progress,
            monotonic_fn=_monotonic,
            consume_headless_jsonl_line_fn=tasks_teammate_runtime.consume_headless_jsonl_line,
            synthetic_response_payload_fn=tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state,
            teammate_response_projection_fn=tasks_teammate_runtime.teammate_response_projection,
            running_summary_text_fn=tasks_teammate_runtime.running_summary_text,
            response_status_mapping_fn=tasks_support_runtime.response_status_mapping,
            mapping_dict_fn=tasks_support_runtime.mapping_dict,
            route_report_from_status_fn=tasks_support_runtime.route_report_from_status,
            teammate_commands_fn=tasks_support_runtime.teammate_commands,
            teammate_test_commands_fn=tasks_support_runtime.teammate_test_commands,
            teammate_modified_files_fn=tasks_support_runtime.teammate_modified_files,
            trim_error_fn=tasks_support_runtime.trim_error,
            subprocess_artifact_fn=lambda payload: dict(payload),
            task_artifact_fn=_task_artifact,
        )

    snapshot_path = tmp_path / "results" / f"{envelope.task_id}_teammate_running.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["terminal_state"] == "running"
    assert payload["summary"] == "running pass #2"
    assert payload["stream_event_count"] == 2
    assert payload["command_policies"] == []
    assert payload["runner_pid"] == 4321
    assert int(payload["worker_pid"]) > 0
    assert str(payload["stdout_path"]).endswith(f"{envelope.task_id}_teammate_stdout.log")
    assert str(payload["stderr_path"]).endswith(f"{envelope.task_id}_teammate_stderr.log")
    assert str(payload["last_event_at"]).strip()

    result = storage.get_result(envelope.task_id)
    assert result is not None
    assert result.status == BackgroundTaskStatus.RUNNING
    assert result.summary == "running pass #2"
    assert result.artifact["running_snapshot_path"] == str(snapshot_path)
    assert result.artifact["terminal_state"] == "running"
    assert result.artifact["command_policies"] == []


def test_terminal_snapshot_keeps_completed_state_with_running_snapshot_metadata(tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_running_to_terminal",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={"task": "finish teammate run"},
    )
    storage.upsert_envelope(envelope, queue_state="running", runner_pid=1001, runner_token="runner-token")

    running_snapshot_path = storage.write_result_snapshot(
        envelope.task_id,
        {
            "status": "running",
            "terminal_state": "running",
            "summary": "running summary",
            "runner_pid": 1001,
            "worker_pid": 2002,
            "stdout_path": str(tmp_path / "results" / f"{envelope.task_id}_teammate_stdout.log"),
            "stderr_path": str(tmp_path / "results" / f"{envelope.task_id}_teammate_stderr.log"),
            "last_event_at": "2026-04-05T10:00:10+00:00",
        },
        suffix="teammate_running",
    )

    run = SubprocessRunResult(
        returncode=0,
        command=["python", "-m", "cli.agent_cli", "--headless", "--jsonl"],
        stdout="",
        stderr="",
        cancelled=False,
        timed_out=False,
        timeout_seconds=1800.0,
        cwd=str(tmp_path),
        stdout_path=Path(tmp_path / "results" / f"{envelope.task_id}_teammate_stdout.log"),
        stderr_path=Path(tmp_path / "results" / f"{envelope.task_id}_teammate_stderr.log"),
    )

    result = tasks_execution_runtime.build_teammate_task_result(
        envelope=envelope,
        storage=storage,
        run=run,
        started_at="2026-04-05T10:00:00+00:00",
        finished_at="2026-04-05T10:00:30+00:00",
        retry_count=0,
        status=BackgroundTaskStatus.COMPLETED,
        summary="completed summary",
        error_text="",
        task_text="finish teammate run",
        response_payload={"assistant_text": "done", "thread_id": "thread_abc"},
        provider="openai",
        model="gpt_54",
        reasoning_effort="high",
        live_cwd=tmp_path,
        allowed_paths=[],
        blocked_paths=[],
        staged_workspace=False,
        bootstrap_artifact={},
        response_status={},
        protocol_diagnostics={},
        route_report={},
        tool_event_names=[],
        modified_files=[],
        commands=[],
        test_commands=[],
        command_policies=[
            {
                "command": "pytest -q tests/test_demo.py",
                "effective_command": "python /tmp/test_lock_runner.py -- pytest -q tests/test_demo.py",
                "status": "completed",
                "policy_denied": False,
                "error_code": "",
                "command_policy": {"allowed": True, "test_policy": "scoped_only"},
            }
        ],
        final_apply_pending=False,
        final_apply_state="not_required",
        out_of_scope_files=[],
        review_commands=[],
        stream_event_count=3,
        stage_cwd=None,
        review_path="",
        assistant_text="done",
        commentary_preview_text="",
        subprocess_progress_payload_fn=lambda **_: {
            "step_count": 1,
            "checkpoint_count": 2,
            "current_step_id": "step_1",
            "current_step_status": "completed",
            "current_step_title": "teammate headless turn",
        },
        background_terminal_state_fn=lambda **_: "completed",
        subprocess_artifact_fn=lambda payload: dict(payload),
        task_artifact_fn=lambda envelope_arg, queue_state, cancel_requested, extra: {
            "task_id": envelope_arg.task_id,
            "queue_state": queue_state,
            "cancel_requested": cancel_requested,
            **dict(extra),
        },
        trim_error_fn=tasks_support_runtime.trim_error,
    )

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["running_snapshot_path"] == str(running_snapshot_path)
    assert result.artifact["runner_pid"] == 1001
    assert result.artifact["worker_pid"] == 2002
    assert result.artifact["last_event_at"] == "2026-04-05T10:00:10+00:00"
    assert result.artifact["command_policies"][0]["effective_command"].startswith("python /tmp/test_lock_runner.py")

    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "completed"
    assert snapshot["terminal_state"] == "completed"
    assert snapshot["running_snapshot_path"] == str(running_snapshot_path)
    assert snapshot["command_policies"][0]["command"] == "pytest -q tests/test_demo.py"
    assert Path(snapshot["response_path"]).exists()


def test_heartbeat_path_writes_minimal_running_snapshot_without_stdout_events(tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_running_snapshot_heartbeat",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={"task": "wait quietly"},
    )
    storage.upsert_envelope(envelope, queue_state="running", runner_pid=8765, runner_token="runner-token")

    state = tasks_teammate_runtime.new_headless_jsonl_state()
    stream_progress: dict[str, object] = {}

    tasks_stream_runtime.ensure_teammate_running_snapshot(
        state=state,
        storage=storage,
        envelope=envelope,
        started_at="2026-04-05T10:05:00+00:00",
        retry_count=0,
        live_cwd=tmp_path,
        provider="openai",
        model="gpt_54",
        reasoning_effort="high",
        allowed_paths=[],
        blocked_paths=[],
        staged_workspace=False,
        bootstrap_artifact={"bootstrap_diagnostics": {"cwd_exists": True}},
        stream_progress=stream_progress,
        synthetic_response_payload_fn=tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state,
        teammate_response_projection_fn=tasks_teammate_runtime.teammate_response_projection,
        running_summary_text_fn=tasks_teammate_runtime.running_summary_text,
        response_status_mapping_fn=tasks_support_runtime.response_status_mapping,
        mapping_dict_fn=tasks_support_runtime.mapping_dict,
        route_report_from_status_fn=tasks_support_runtime.route_report_from_status,
        teammate_commands_fn=tasks_support_runtime.teammate_commands,
        teammate_test_commands_fn=tasks_support_runtime.teammate_test_commands,
        teammate_modified_files_fn=tasks_support_runtime.teammate_modified_files,
        trim_error_fn=tasks_support_runtime.trim_error,
        subprocess_artifact_fn=lambda payload: dict(payload),
        task_artifact_fn=lambda envelope_arg, queue_state, cancel_requested, extra: {
            "task_id": envelope_arg.task_id,
            "queue_state": queue_state,
            "cancel_requested": cancel_requested,
            **dict(extra),
        },
    )

    snapshot_path = tmp_path / "results" / f"{envelope.task_id}_teammate_running.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["terminal_state"] == "running"
    assert payload["summary"] == "running"
    assert payload["stream_event_count"] == 0
    assert payload["runner_pid"] == 8765
    assert int(payload["worker_pid"]) > 0
    assert stream_progress["has_running_snapshot"] is True
