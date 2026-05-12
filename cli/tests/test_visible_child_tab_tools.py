from __future__ import annotations

import json

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_core.orchestration_commands import handle_orchestration_command


class _VisibleChildBackend:
    active_tab_id = "main"
    _tab_order = ["main", "tab-2", "tab-3"]
    _tabs = {"main": object(), "tab-2": object(), "tab-3": object()}

    def __init__(self) -> None:
        self.dispatch_calls: list[dict[str, object]] = []
        self.send_calls: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []
        self.child_ids = ["tab-2"]

    def display_tab_label(self, tab_id: str) -> str:
        return {"main": "1", "tab-2": "2", "tab-3": "3"}.get(tab_id, tab_id)

    def child_tab_ids(self, parent_tab_id: str) -> list[str]:
        return list(self.child_ids) if parent_tab_id == "main" else []

    def dispatch_visible_child_task(self, **kwargs):
        self.dispatch_calls.append(dict(kwargs))
        return {
            "tab_id": "tab-2",
            "task_id": "run_visible:README:0",
            "provider_name": "openai",
            "model": "gpt-5.4",
            "route_label": "dispatch_visible_child_tab",
        }

    def send_visible_child_task(self, **kwargs):
        self.send_calls.append(dict(kwargs))
        metadata = kwargs.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "tab_id": kwargs["child_tab_id"],
            "parent_tab_id": kwargs["parent_tab_id"],
            "task_run_id": metadata.get("agenthub_task_run_id", ""),
            "queued": True,
            "priority": "now" if kwargs.get("interrupt") else "next",
            "route_label": "send_visible_child_tab",
        }

    def visible_child_task_run_snapshots(self, parent_tab_id: str):
        assert parent_tab_id == "main"
        return list(self.snapshots)


class _Runtime:
    def __init__(self, backend: _VisibleChildBackend) -> None:
        self.visible_child_tab_backend = backend
        self.visible_child_parent_tab_id = "main"


def test_internal_spawn_child_tab_dispatches_visible_child_task() -> None:
    backend = _VisibleChildBackend()
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__spawn_child_tab",
        arg_text=json.dumps(
            {
                "task": "Inspect README",
                "task_name": "README",
                "metadata": {"run_id": "run_visible"},
            }
        ),
    )

    assert isinstance(result, CommandExecutionResult)
    assert result.tool_events[0].name == "spawn_child_tab"
    assert result.tool_events[0].payload["tab_id"] == "tab-2"
    assert "visible child tab spawned" in result.assistant_text
    assert backend.dispatch_calls == [
        {
            "parent_tab_id": "main",
            "task_text": "Inspect README",
            "metadata": {
                "run_id": "run_visible",
                "card_id": "README",
                "source": "spawn_child_tab",
            },
        }
    ]


def test_internal_send_child_tab_resolves_latest_child_and_queues_message() -> None:
    backend = _VisibleChildBackend()
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__send_child_tab",
        arg_text=json.dumps(
            {
                "target": "latest",
                "message": "Continue with docs",
                "interrupt": True,
            }
        ),
    )

    assert isinstance(result, CommandExecutionResult)
    assert result.tool_events[0].name == "send_child_tab"
    assert result.tool_events[0].payload["tab_id"] == "tab-2"
    assert "task_run_id" in result.tool_events[0].payload
    assert backend.send_calls == [
        {
            "parent_tab_id": "main",
            "child_tab_id": "tab-2",
            "task_text": "Continue with docs",
            "interrupt": True,
            "metadata": {"source": "send_child_tab"},
        }
    ]


def test_internal_send_child_tab_preserves_assignment_ref_metadata() -> None:
    backend = _VisibleChildBackend()
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__send_child_tab",
        arg_text=json.dumps(
            {
                "target": "latest",
                "message": "Continue with tests",
                "metadata": {
                    "run_id": "run_visible",
                    "card_id": "FOLLOWUP",
                    "attempt": 1,
                },
            }
        ),
    )

    assert isinstance(result, CommandExecutionResult)
    assert backend.send_calls[0]["metadata"] == {
        "run_id": "run_visible",
        "card_id": "FOLLOWUP",
        "attempt": 1,
        "orchestration": {
            "run_id": "run_visible",
            "card_id": "FOLLOWUP",
            "attempt": 1,
        },
        "source": "send_child_tab",
    }


def test_internal_wait_child_tasks_returns_taskrun_snapshots_without_transcript_scraping() -> None:
    backend = _VisibleChildBackend()
    backend.snapshots = [
        {
            "run_id": "tab-2-run-1",
            "tab_id": "tab-2",
            "state": "completed",
            "terminal_state": "completed",
            "objective_state": "claimed_done",
            "summary": "README inspected.",
            "assignment_ref": {"run_id": "run_visible", "card_id": "README", "attempt": 0},
        }
    ]
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__wait_child_tasks",
        arg_text=json.dumps({"targets": ["run_visible:README:0"], "timeout_ms": 0}),
    )

    assert isinstance(result, CommandExecutionResult)
    assert result.tool_events[0].name == "wait_child_tasks"
    payload = result.tool_events[0].payload
    assert payload["parent_tab_id"] == "main"
    assert payload["child_count"] == 1
    assert payload["task_runs"][0]["summary"] == "README inspected."
    assert "terminal_count=1" in result.assistant_text


def test_internal_wait_child_tasks_resolves_latest_child_selector() -> None:
    backend = _VisibleChildBackend()
    backend.snapshots = [
        {
            "run_id": "tab-2-run-1",
            "tab_id": "tab-2",
            "state": "completed",
            "terminal_state": "completed",
            "objective_state": "claimed_done",
            "summary": "latest child done.",
            "assignment_ref": {},
        }
    ]
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__wait_child_tasks",
        arg_text=json.dumps({"targets": ["latest"], "timeout_ms": 0}),
    )

    assert isinstance(result, CommandExecutionResult)
    payload = result.tool_events[0].payload
    assert payload["targets"] == ["tab-2"]
    assert payload["task_runs"][0]["summary"] == "latest child done."


def test_internal_wait_child_tasks_uses_latest_snapshot_for_tab_target() -> None:
    backend = _VisibleChildBackend()
    backend.snapshots = [
        {
            "run_id": "tab-2-run-1",
            "tab_id": "tab-2",
            "state": "completed",
            "terminal_state": "completed",
            "objective_state": "claimed_done",
            "summary": "old completed task.",
            "assignment_ref": {},
        },
        {
            "run_id": "tab-2-run-2",
            "tab_id": "tab-2",
            "state": "queued",
            "terminal_state": "",
            "objective_state": "not_reported",
            "summary": "",
            "assignment_ref": {},
        },
    ]
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__wait_child_tasks",
        arg_text=json.dumps({"targets": ["2"], "timeout_ms": 0, "wait_for": "all"}),
    )

    assert isinstance(result, CommandExecutionResult)
    payload = result.tool_events[0].payload
    assert payload["task_runs"][0]["run_id"] == "tab-2-run-2"
    assert payload["selected_task_run_ids"] == ["tab-2-run-2"]
    assert payload["pending_count"] == 1
    assert payload["terminal_count"] == 0
    assert payload["timed_out"] is True


def test_internal_wait_child_tasks_any_returns_when_one_latest_child_is_terminal() -> None:
    backend = _VisibleChildBackend()
    backend.child_ids = ["tab-2", "tab-3"]
    backend.snapshots = [
        {
            "run_id": "tab-2-run-1",
            "tab_id": "tab-2",
            "state": "completed",
            "terminal_state": "completed",
            "objective_state": "claimed_done",
            "summary": "README done.",
            "assignment_ref": {},
        },
        {
            "run_id": "tab-3-run-1",
            "tab_id": "tab-3",
            "state": "running",
            "terminal_state": "",
            "objective_state": "not_reported",
            "summary": "",
            "assignment_ref": {},
        },
    ]
    runtime = _Runtime(backend)

    result = handle_orchestration_command(
        runtime,
        name="__wait_child_tasks",
        arg_text=json.dumps(
            {
                "targets": ["2", "3"],
                "timeout_ms": 0,
                "wait_for": "any",
            }
        ),
    )

    assert isinstance(result, CommandExecutionResult)
    payload = result.tool_events[0].payload
    assert payload["wait_for"] == "any"
    assert payload["selected_task_run_ids"] == ["tab-2-run-1", "tab-3-run-1"]
    assert payload["pending_count"] == 1
    assert payload["terminal_count"] == 1
    assert payload["timed_out"] is False
