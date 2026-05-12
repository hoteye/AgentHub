from __future__ import annotations

from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui.tab_task_run import (
    TabTaskRun,
    objective_state_from_response,
    queued_task_run,
    task_run_from_exception,
    task_run_from_response,
)


def test_prompt_response_completed_maps_to_agenthub_task_completed() -> None:
    run = queued_task_run(run_id="run-1", tab_id="main", user_prompt="hi")
    run.mark_running(started_at=1.0)

    result = task_run_from_response(
        run,
        PromptResponse(user_text="hi", assistant_text="hello"),
        transcript_range=(0, 2),
    )

    assert result.state == "completed"
    assert result.terminal_state == "completed"
    assert result.terminal_reason == "provider_completed"
    assert result.objective_state == "not_reported"
    assert result.transcript_range == (0, 2)


def test_codex_turn_failed_maps_to_failed_without_using_codex_as_global_standard() -> None:
    run = queued_task_run(run_id="run-1", tab_id="main")

    result = task_run_from_response(
        run,
        PromptResponse(
            user_text="hi",
            assistant_text="",
            turn_events=[
                {"type": "turn.failed", "error": {"message": "provider failed"}},
            ],
        ),
    )

    assert result.state == "failed"
    assert result.terminal_state == "failed"
    assert result.terminal_reason == "turn_failed"
    assert result.error_message == "provider failed"
    assert result.provider_terminal_event == {
        "type": "turn.failed",
        "error": {"message": "provider failed"},
    }


def test_provider_degraded_fallback_is_completed_with_degraded_reason() -> None:
    run = queued_task_run(run_id="run-1", tab_id="main")

    result = task_run_from_response(
        run,
        PromptResponse(
            user_text="hi",
            assistant_text="fallback answer",
            protocol_diagnostics={"protocol_path": {"kind": "provider_degraded_fallback"}},
        ),
    )

    assert result.terminal_state == "completed"
    assert result.terminal_reason == "provider_degraded"


def test_approval_request_is_waiting_not_terminal() -> None:
    run = queued_task_run(run_id="run-1", tab_id="main")

    result = task_run_from_response(
        run,
        PromptResponse(
            user_text="run command",
            assistant_text="approval requested",
            tool_events=[
                ToolEvent(
                    name="shell_approval_requested",
                    ok=False,
                    summary="approval requested",
                )
            ],
        ),
    )

    assert result.state == "waiting_approval"
    assert result.terminal_state == ""
    assert result.terminal_reason == "waiting_approval"
    assert not result.is_terminal


def test_exception_maps_to_failed_task_run() -> None:
    run = queued_task_run(run_id="run-1", tab_id="main")

    result = task_run_from_exception(run, RuntimeError("boom"))

    assert result.state == "failed"
    assert result.terminal_state == "failed"
    assert result.terminal_reason == "runtime_exception"
    assert result.error_message == "boom"


def test_objective_state_requires_structured_status_not_free_text_guessing() -> None:
    response = PromptResponse(
        user_text="task",
        assistant_text="Done.",
        status={"objective_state": "claimed_done"},
    )

    assert objective_state_from_response(response) == "claimed_done"
    assert (
        objective_state_from_response(PromptResponse(user_text="task", assistant_text="Done."))
        == "not_reported"
    )


def test_task_run_round_trip_serializes_status_and_terminal_event() -> None:
    run = TabTaskRun(
        run_id="run-1",
        tab_id="child",
        parent_tab_id="master",
        provider="openai",
        engine="codex_sidecar",
        state="completed",
        terminal_state="completed",
        terminal_reason="turn_completed",
        objective_state="claimed_partial",
        started_at=1.0,
        finished_at=2.0,
        user_prompt="inspect",
        summary="partial",
        transcript_range=(3, 5),
        provider_terminal_event={"type": "turn.completed"},
        status_snapshot={"provider_name": "openai"},
    )

    restored = TabTaskRun.from_dict(run.to_dict())

    assert restored == run
