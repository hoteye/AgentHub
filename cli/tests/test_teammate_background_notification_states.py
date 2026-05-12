from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from cli.agent_cli.runtime_services import delegated_agent_background_runtime


class _MemoryStorage:
    def __init__(self) -> None:
        self.results: dict[str, Any] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}

    def get_result(self, task_id: str) -> Any | None:
        return self.results.get(task_id)

    def write_result_snapshot(self, task_id: str, payload: dict[str, Any], *, suffix: str = "delegated") -> str:
        del suffix
        self.snapshots[task_id] = dict(payload)
        return f"/tmp/{task_id}.json"

    def upsert_result(self, result: Any) -> None:
        self.results[result.task_id] = result


class _RuntimeStub:
    def __init__(self) -> None:
        self.storage = _MemoryStorage()
        self._adapter = SimpleNamespace(storage=self.storage)
        self.payload: dict[str, Any] = {}
        self.progress_payload: dict[str, Any] = {}

    def _background_task_adapter_if_enabled(self) -> Any:
        return self._adapter

    def _delegated_agent_payload(self, session: Any) -> dict[str, Any]:
        del session
        return dict(self.payload)

    def _delegated_progress_summary(self, session: Any, *, include_history: bool = True) -> dict[str, Any]:
        del session, include_history
        return dict(self.progress_payload)

    @staticmethod
    def _delegated_background_task_status(status: str, *, has_text: bool, terminal_reason: str = "") -> str:
        return delegated_agent_background_runtime.delegated_background_task_status(
            status,
            has_text=has_text,
            terminal_reason=terminal_reason,
        )

    @staticmethod
    def _delegated_background_notification_state(*, status: str, adopted: bool, terminal_reason: str) -> str:
        return delegated_agent_background_runtime.delegated_background_notification_state(
            status=status,
            adopted=adopted,
            terminal_reason=terminal_reason,
        )

    @staticmethod
    def _delegated_background_task_id(session: Any) -> str:
        return delegated_agent_background_runtime.delegated_background_task_id(session)

    @staticmethod
    def _delegated_goal_text(session: Any) -> str:
        del session
        return "background-goal"

    @staticmethod
    def _delegated_agent_summary_text(session: Any) -> str:
        return f"delegated summary for {session.agent_id}"


def _session() -> SimpleNamespace:
    return SimpleNamespace(agent_id="agent_1", role="teammate", delegation_mode="background")


def _sync(runtime: _RuntimeStub, session: Any) -> Any:
    delegated_agent_background_runtime.sync_delegated_background_task(
        runtime,
        session,
        preview_text_fn=lambda text, max_chars=160: str(text or "")[: max(0, int(max_chars or 0))],
    )
    return runtime.storage.get_result(f"bg_delegate_{session.agent_id}")


def test_ready_to_foreground_adopted_progression_is_stable() -> None:
    runtime = _RuntimeStub()
    session = _session()
    runtime.payload = {
        "status": "completed",
        "text": "answer",
        "error": "",
        "terminal_reason": "completed",
        "terminal_state": "completed",
        "adopted": False,
        "created_at": "2026-04-06T00:00:00+00:00",
        "updated_at": "2026-04-06T00:00:01+00:00",
        "result_contract": {"summary": "ready"},
    }
    runtime.progress_payload = {
        "step_count": 1,
        "checkpoint_count": 4,
        "workflow_state": "completed",
    }
    ready = _sync(runtime, session)
    assert ready is not None
    assert ready.artifact["notification_state"] == "ready"

    runtime.payload.update(
        {
            "adopted": True,
            "adopted_at": "2026-04-06T00:00:02+00:00",
            "result_contract": {"summary": "adopted"},
            "updated_at": "2026-04-06T00:00:02+00:00",
        }
    )
    runtime.progress_payload["checkpoint_count"] = 5
    adopted = _sync(runtime, session)
    assert adopted is not None
    assert adopted.artifact["notification_state"] == "foreground_adopted"
    assert adopted.artifact["foreground_taken_over_at"] == "2026-04-06T00:00:02+00:00"
    assert int(adopted.artifact["checkpoint_count"]) == 5


def test_repeated_wait_sync_is_idempotent_without_checkpoint_drift() -> None:
    runtime = _RuntimeStub()
    session = _session()
    runtime.payload = {
        "status": "completed",
        "text": "answer",
        "terminal_reason": "completed",
        "terminal_state": "completed",
        "adopted": True,
        "adopted_at": "2026-04-06T00:00:03+00:00",
        "created_at": "2026-04-06T00:00:00+00:00",
        "updated_at": "2026-04-06T00:00:03+00:00",
        "result_contract": {"summary": "adopted"},
    }
    runtime.progress_payload = {
        "step_count": 1,
        "checkpoint_count": 6,
        "workflow_state": "completed",
    }
    first = _sync(runtime, session)
    assert first is not None
    first_checkpoint_count = int(first.artifact["checkpoint_count"])
    assert first.artifact["notification_state"] == "foreground_adopted"

    runtime.payload.update(
        {
            "adopted": False,
            "adopted_at": "",
            "result_contract": {"summary": "stale-ready"},
        }
    )
    runtime.progress_payload["checkpoint_count"] = first_checkpoint_count
    repeated = _sync(runtime, session)
    assert repeated is not None
    assert repeated.artifact["notification_state"] == "foreground_adopted"
    assert int(repeated.artifact["checkpoint_count"]) == first_checkpoint_count


def test_role_override_orphan_mirror_remains_orphaned_across_stale_sync() -> None:
    runtime = _RuntimeStub()
    session = _session()
    runtime.payload = {
        "status": "running",
        "text": "",
        "error": "",
        "terminal_reason": "",
        "terminal_state": "",
        "adopted": False,
        "created_at": "2026-04-06T00:00:00+00:00",
        "updated_at": "2026-04-06T00:00:01+00:00",
        "result_contract": {"summary": "running"},
    }
    runtime.progress_payload = {
        "step_count": 1,
        "checkpoint_count": 2,
        "workflow_state": "running",
    }
    _sync(runtime, session)

    runtime.payload.update(
        {
            "status": "closed",
            "terminal_reason": "role_override_changed",
            "terminal_state": "orphaned",
            "adopted": True,
            "updated_at": "2026-04-06T00:00:04+00:00",
            "result_contract": {"summary": "should not override orphan summary"},
        }
    )
    runtime.progress_payload["checkpoint_count"] = 3
    orphaned = _sync(runtime, session)
    assert orphaned is not None
    assert orphaned.status.value == "cancelled"
    assert orphaned.artifact["notification_state"] == "orphaned"
    assert orphaned.artifact["terminal_state"] == "orphaned"
    assert orphaned.artifact["terminal_reason"] == "role_override_changed"

    runtime.payload.update(
        {
            "status": "completed",
            "terminal_reason": "",
            "terminal_state": "",
            "adopted": True,
            "result_contract": {"summary": "late completed mirror"},
        }
    )
    runtime.progress_payload["checkpoint_count"] = 3
    stale = _sync(runtime, session)
    assert stale is not None
    assert stale.status.value == "cancelled"
    assert stale.artifact["notification_state"] == "orphaned"
    assert stale.artifact["terminal_state"] == "orphaned"
    assert stale.artifact["terminal_reason"] == "role_override_changed"
