from __future__ import annotations

from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.runtime_services import (
    run_thread_normalization_helpers_runtime,
    runtime_response_runtime,
)


class _RuntimeStub:
    selected_conversation = None

    @staticmethod
    def _plan_activity_event(plan):
        del plan
        return None


def _normalized_turn_event_value(value):
    return run_thread_normalization_helpers_runtime.normalized_turn_event_value(
        value,
        normalize_nested_value_fn=_normalized_turn_event_value,
    )


def test_turn_event_replay_signature_treats_phase_less_agent_message_as_final_answer() -> None:
    streamed_event = {
        "type": "item.completed",
        "item": {"id": "streamed", "type": "agent_message", "text": "done"},
    }
    backfill_event = {
        "type": "item.completed",
        "item": {
            "id": "backfill",
            "type": "agent_message",
            "text": "done",
            "phase": "final_answer",
        },
    }

    assert run_thread_normalization_helpers_runtime.turn_event_replay_signature(
        streamed_event,
        normalized_turn_event_value_fn=_normalized_turn_event_value,
    ) == run_thread_normalization_helpers_runtime.turn_event_replay_signature(
        backfill_event,
        normalized_turn_event_value_fn=_normalized_turn_event_value,
    )


def test_build_activity_events_recognizes_exec_command_source_text() -> None:
    activities = runtime_response_runtime.build_activity_events(
        _RuntimeStub(),
        source_text="/exec_command --workdir cli 'python -V' --yield-time-ms 250",
        tool_events=[],
        handled_as_command=True,
        plan=None,
    )

    assert len(activities) == 1
    assert activities[0].title == "Running python -V"
    assert activities[0].params == {"command": "python -V", "command_display": "python -V"}


def test_build_activity_events_strips_shell_start_prefix_from_running_activity() -> None:
    activities = runtime_response_runtime.build_activity_events(
        _RuntimeStub(),
        source_text="/shell start python -i",
        tool_events=[],
        handled_as_command=True,
        plan=None,
    )

    assert len(activities) == 1
    assert activities[0].title == "Running python -i"
    assert activities[0].params == {"command": "python -i", "command_display": "python -i"}


def test_build_activity_events_compacts_compound_command_title_for_external_surfaces() -> None:
    activities = runtime_response_runtime.build_activity_events(
        _RuntimeStub(),
        source_text="/exec_command 'cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1'",
        tool_events=[],
        handled_as_command=True,
        plan=None,
    )

    assert len(activities) == 1
    assert activities[0].title == "Running git fetch upstream / git merge upstream/main --no-edit"
    assert activities[0].params == {
        "command": "cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1",
        "command_display": "git fetch upstream / git merge upstream/main --no-edit",
    }


def test_prompt_response_defaults_command_display_text_from_assistant_summary() -> None:
    response = PromptResponse(
        user_text="/model",
        assistant_text="current_model=gpt-5.5\nmodel_key=gpt_55",
        handled_as_command=True,
    )

    assert response.command_display_text == "current_model=gpt-5.5"


def test_prompt_response_does_not_default_command_display_text_for_list_output() -> None:
    response = PromptResponse(
        user_text="/models",
        assistant_text="models=2\n- gpt_55: GPT-5.5\n- claude_sonnet_46: Claude Sonnet 4.6",
        handled_as_command=True,
    )

    assert response.command_display_text == ""


def test_prompt_response_defaults_command_display_text_from_tool_summary() -> None:
    response = PromptResponse(
        user_text="/shell echo ok",
        assistant_text="",
        tool_events=[
            ToolEvent(
                name="shell",
                ok=True,
                summary="shell rc=0",
                payload={"stdout": "ok\n"},
            )
        ],
        handled_as_command=True,
    )

    assert response.command_display_text == "shell rc=0"
