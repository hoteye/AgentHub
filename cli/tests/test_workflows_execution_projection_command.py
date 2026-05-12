from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.runtime_core import background_task_commands as module
from cli.agent_cli.runtime_runs import RunKind
from cli.agent_cli.runtime_runs.manager import RunManager


class _RuntimeStub:
    def __init__(self) -> None:
        self.cwd = Path("/tmp/demo")
        self.run_manager = RunManager()

    @staticmethod
    def _delegated_agent_state_snapshot():
        return []

    @staticmethod
    def list_orchestration_workflows(*, limit: int = 20) -> tuple[list[str], int]:
        del limit
        return ([], 0)


def test_workflows_text_includes_execution_projection_counts_from_run_manager() -> None:
    runtime = _RuntimeStub()
    runtime.run_manager.create(run_id="turn_1", kind=RunKind.TURN, thread_id="thread_1")
    runtime.run_manager.finish("turn_1", summary="turn done")

    runtime.run_manager.create(run_id="bg_1", kind=RunKind.BACKGROUND, thread_id="thread_1")
    runtime.run_manager.update("bg_1", status="running", summary="background running")

    runtime.run_manager.create(run_id="task_1", kind=RunKind.TASK, thread_id="thread_1")
    runtime.run_manager.timeout("task_1", summary="task timed out")

    runtime.run_manager.create(run_id="wf_1", kind=RunKind.WORKFLOW, thread_id="thread_1")
    runtime.run_manager.finish("wf_1", failed=True, summary="workflow failed")

    fake_adapter = SimpleNamespace(
        config=SimpleNamespace(enabled=False, provider="huey"),
        queue=SimpleNamespace(provider_label="huey-immediate"),
        list_recent=lambda limit: [],
    )

    with patch("cli.agent_cli.background_tasks.build_background_task_adapter", return_value=fake_adapter):
        text = module._workflows_text(runtime, limit=5)

    assert "execution_projection_runs=3" in text
    assert "execution_projection_running=1" in text
    assert "execution_projection_failed=1" in text
    assert "execution_projection_timed_out=1" in text
    assert "execution_projection_completed=0" in text
