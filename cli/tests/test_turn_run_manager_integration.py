from __future__ import annotations

import pytest
from pathlib import Path

from cli.agent_cli.models import AgentIntent, CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_runs import RunKind, RunStatus
from cli.agent_cli.thread_store import ThreadStore


class _TurnAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "test-provider",
            "provider_model": "test-model",
            "provider_planner": "openai_chat",
            "model_key": "test-model",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None, input_items=None, **kwargs):
        del history, tool_executor, attachments, input_items, kwargs
        if self.fail:
            raise RuntimeError("boom")
        return AgentIntent(assistant_text=f"echo: {text}")


def test_turn_run_manager_marks_completed_for_successful_prompt(tmp_path: Path) -> None:
    runtime = AgentCliRuntime(agent=_TurnAgent(), thread_store=ThreadStore(tmp_path / "state"))

    runtime.start_thread(name="turn-success")
    response = runtime.handle_prompt("hello")

    assert response.assistant_text == "echo: hello"
    runs = runtime.run_manager.list()
    assert len(runs) == 1
    run = runs[0]
    assert run.kind is RunKind.TURN
    assert run.status is RunStatus.COMPLETED
    assert run.thread_id == str(runtime.thread_id or "")
    assert run.payload["user_text"] == "hello"
    assert run.payload["assistant_text"] == "echo: hello"


def test_turn_run_manager_marks_failed_when_prompt_raises(tmp_path: Path) -> None:
    runtime = AgentCliRuntime(agent=_TurnAgent(fail=True), thread_store=ThreadStore(tmp_path / "state"))

    runtime.start_thread(name="turn-failed")
    with pytest.raises(RuntimeError, match="boom"):
        runtime.handle_prompt("explode")

    runs = runtime.run_manager.list()
    assert len(runs) == 1
    run = runs[0]
    assert run.kind is RunKind.TURN
    assert run.status is RunStatus.FAILED
    assert run.payload["error_type"] == "RuntimeError"
    assert run.payload["error_text"] == "boom"


def test_turn_run_manager_marks_cancelled_for_interrupt_result(tmp_path: Path) -> None:
    runtime = AgentCliRuntime(agent=_TurnAgent(), thread_store=ThreadStore(tmp_path / "state"))

    runtime.start_thread(name="turn-cancelled")
    runtime._run_command_text_result = lambda text: CommandExecutionResult(
        assistant_text="interrupted",
        tool_events=[
            ToolEvent(
                name="interrupted",
                ok=False,
                summary="execution interrupted",
                payload={"reason": "user_interrupt"},
            )
        ],
    )

    response = runtime.handle_prompt("/noop")

    assert response.assistant_text == "interrupted"
    runs = runtime.run_manager.list()
    assert len(runs) == 1
    run = runs[0]
    assert run.kind is RunKind.TURN
    assert run.status is RunStatus.CANCELLED
    assert run.payload["assistant_text"] == "interrupted"


def test_turn_run_manager_marks_timed_out_for_wait_timeout_result(tmp_path: Path) -> None:
    runtime = AgentCliRuntime(agent=_TurnAgent(), thread_store=ThreadStore(tmp_path / "state"))

    runtime.start_thread(name="turn-timeout")
    runtime._run_command_text_result = lambda text: CommandExecutionResult(
        assistant_text="wait timed out",
        tool_events=[
            ToolEvent(
                name="wait_agent",
                ok=False,
                summary="wait timed out",
                payload={"wait_timed_out": True, "reason": "blocking_join"},
            )
        ],
    )

    response = runtime.handle_prompt("/wait_agent agent_x")

    assert response.assistant_text == "wait timed out"
    runs = runtime.run_manager.list()
    assert len(runs) == 1
    run = runs[0]
    assert run.kind is RunKind.TURN
    assert run.status is RunStatus.TIMED_OUT
    assert run.payload["assistant_text"] == "wait timed out"
