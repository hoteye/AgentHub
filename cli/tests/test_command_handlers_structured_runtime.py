from __future__ import annotations

import json
from types import SimpleNamespace

from cli.agent_cli.runtime_core.command_dispatch import run_command_text_result
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (  # noqa: E402
    handle_request_user_input_command,
    handle_update_plan_command,
)
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (  # noqa: E402
    normalize_request_user_input_questions,
)
from cli.agent_cli.runtime_core.tool_call_context_runtime import (  # noqa: E402
    active_provider_tool_call_id,
)


class _PluginTools:
    def run_plugin_command(self, name, arg_text, runtime):
        del name, arg_text, runtime
        return (
            "summary line\n"
            "detail_key=value\n"
            "another_detail=value",
            [],
        )


class _PluginRuntime:
    tools = _PluginTools()

    @staticmethod
    def _is_interrupt_requested() -> bool:
        return False


def test_run_command_text_result_adds_default_display_text_for_slash_commands() -> None:
    slash_result = run_command_text_result(_PluginRuntime(), "/plugin_status")
    plain_result = run_command_text_result(_PluginRuntime(), "plugin_status")

    assert slash_result.assistant_text == "summary line\ndetail_key=value\nanother_detail=value"
    assert slash_result.command_display_text == "summary line"
    assert plain_result.assistant_text == slash_result.assistant_text
    assert plain_result.command_display_text == ""


def test_run_command_text_result_keeps_list_outputs_uncompressed() -> None:
    class _ListPluginTools:
        def run_plugin_command(self, name, arg_text, runtime):
            del name, arg_text, runtime
            return ("items=2\n- first\n- second", [])

    runtime = SimpleNamespace(tools=_ListPluginTools())
    runtime._is_interrupt_requested = lambda: False

    result = run_command_text_result(runtime, "/plugin_list")

    assert result.assistant_text == "items=2\n- first\n- second"
    assert result.command_display_text == ""


def test_slash_command_turn_events_use_default_display_text() -> None:
    result = run_command_text_result(_PluginRuntime(), "/plugin_status")

    agent_messages = [
        event["item"]["text"]
        for event in result.turn_events
        if isinstance(event, dict)
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "agent_message"
    ]

    assert result.assistant_text == "summary line\ndetail_key=value\nanother_detail=value"
    assert result.command_display_text == "summary line"
    assert agent_messages == ["summary line"]


def test_handle_update_plan_command_rejects_multiple_in_progress_steps() -> None:
    runtime = SimpleNamespace(collaboration_mode="default")

    result = handle_update_plan_command(
        runtime,
        arg_text='{"plan":[{"step":"inspect","status":"in_progress"},{"step":"patch","status":"in_progress"}]}',
    )

    assert result.assistant_text == "failed to parse function arguments: at most one step can be in_progress"
    assert result.tool_events[0].name == "update_plan"
    assert result.tool_events[0].ok is False
    assert result.tool_events[0].payload["function_call_output"] == result.assistant_text
    assert result.item_events[-1]["item"]["type"] == "todo_list"

def test_handle_request_user_input_command_normalizes_questions_in_default_mode() -> None:
    captured_payload: dict[str, object] = {}

    def _handler(payload: dict[str, object]) -> dict[str, object]:
        captured_payload.update(payload)
        return {
            "answers": {"confirm_path": {"answers": ["yes"]}},
            "questions": payload["questions"],
        }

    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=_handler,
    )

    result = handle_request_user_input_command(
        runtime,
        arg_text=(
            '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
            '"options":[{"label":"Yes","description":"Continue."}]}]}'
        ),
    )

    response = json.loads(result.assistant_text)
    assert response["answers"]["confirm_path"]["answers"] == ["yes"]
    assert captured_payload["questions"] == result.tool_events[0].payload["questions"]
    assert result.tool_events[0].payload["questions"][0]["is_other"] is True


def test_normalize_request_user_input_questions_rejects_invalid_option_payload() -> None:
    try:
        normalize_request_user_input_questions(
            [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed?",
                    "options": [{"label": "Yes"}],
                }
            ]
        )
    except ValueError as exc:
        assert str(exc) == "request_user_input requires non-empty options for every question"
    else:
        raise AssertionError("expected ValueError for invalid option payload")


def test_handle_request_user_input_command_normalizes_response_answers_shape() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {"answers": {"confirm_path": "yes"}},
    )

    result = handle_request_user_input_command(
        runtime,
        arg_text=(
            '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
            '"options":[{"label":"Yes","description":"Continue."}]}]}'
        ),
    )

    response = json.loads(result.assistant_text)
    assert response["answers"]["confirm_path"]["answers"] == ["yes"]
    assert result.tool_events[0].payload["response"]["answers"]["confirm_path"]["answers"] == ["yes"]


def test_handle_request_user_input_command_preserves_active_provider_call_id_in_tool_and_item_events() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="plan",
        default_mode_request_user_input=False,
        request_user_input_handler=lambda _payload: {"answers": {"confirm_path": "yes"}},
    )

    with active_provider_tool_call_id("call_request_user_input_1"):
        result = handle_request_user_input_command(
            runtime,
            arg_text=(
                '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
                '"options":[{"label":"Yes","description":"Continue."}]}]}'
            ),
        )

    assert result.tool_events[0].payload["provider_call_id"] == "call_request_user_input_1"
    assert result.item_events[0]["item"]["call_id"] == "call_request_user_input_1"
    assert result.item_events[-1]["item"]["call_id"] == "call_request_user_input_1"


def test_handle_update_plan_command_preserves_active_provider_call_id_on_todo_item() -> None:
    runtime = SimpleNamespace(collaboration_mode="default")

    with active_provider_tool_call_id("call_update_plan_1"):
        result = handle_update_plan_command(
            runtime,
            arg_text='{"plan":[{"step":"inspect","status":"in_progress"}]}',
        )

    assert result.tool_events[0].payload["provider_call_id"] == "call_update_plan_1"
    assert result.item_events[0]["item"]["call_id"] == "call_update_plan_1"
    assert result.item_events[-1]["item"]["type"] == "function_call_output"
    assert result.item_events[-1]["item"]["call_id"] == "call_update_plan_1"
    assert result.item_events[-1]["item"]["output"] == "Plan updated"


def test_handle_update_plan_command_plan_mode_rejection_emits_model_visible_output() -> None:
    runtime = SimpleNamespace(collaboration_mode="plan")

    with active_provider_tool_call_id("call_update_plan_blocked"):
        result = handle_update_plan_command(
            runtime,
            arg_text='{"plan":[{"step":"inspect","status":"in_progress"}]}',
        )

    assert result.assistant_text == "update_plan is a TODO/checklist tool and is not allowed in Plan mode"
    assert result.tool_events[0].payload["function_call_output"] == result.assistant_text
    assert result.item_events[-1]["item"]["type"] == "function_call_output"
    assert result.item_events[-1]["item"]["call_id"] == "call_update_plan_blocked"
    assert result.item_events[-1]["item"]["success"] is False
    assert result.item_events[-1]["item"]["output"] == result.assistant_text
