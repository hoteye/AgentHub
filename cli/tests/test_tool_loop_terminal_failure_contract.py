from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.app_server_protocol_pure_helpers_runtime import (
    completed_turn_status,
    turn_error_message,
)
from cli.agent_cli.headless_runtime import exit_code_for_response
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.models_response_items import compose_turn_events_from_response_items, prompt_response_turn_events
from cli.agent_cli.providers.openai_planner_runtime_helpers_runtime import build_terminal_handler
from cli.agent_cli.providers.openai_planner_runtime_projection_helpers_runtime import fallback_tool_intent


def _compose_turn_events(*, assistant_text, response_items, executed_item_events):
    return compose_turn_events_from_response_items(
        assistant_text=assistant_text,
        response_items=list(response_items or []),
        executed_item_events=list(executed_item_events or []),
    )


def test_prompt_response_turn_events_emit_turn_failed_for_failed_terminal_state() -> None:
    response = PromptResponse(
        user_text="summarize",
        assistant_text="工具已执行完成，但回答阶段未产出可展示内容。",
        status={
            "terminal_state": "failed",
            "error": "工具已执行完成，但最终回答阶段未产出可展示内容。",
        },
    )

    events = prompt_response_turn_events(response)

    assert events[-1] == {
        "type": "turn.failed",
        "error": {"message": "工具已执行完成，但最终回答阶段未产出可展示内容。"},
    }


def test_fallback_tool_intent_marks_missing_final_answer_as_failed() -> None:
    intent = fallback_tool_intent(
        executed_events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={"command": "pwd"},
            )
        ],
        executed_item_events=[],
        compose_turn_events_fn=_compose_turn_events,
    )

    assert intent.status_hint == "degraded"
    assert intent.protocol_diagnostics["turn_terminal_state"]["reason"] == "final_answer_missing"
    assert intent.turn_events[-1]["type"] == "turn.failed"
    assert "最后一个命令" in intent.assistant_text


def test_build_terminal_handler_surfaces_synthesis_exception_as_failed_fallback() -> None:
    planner = SimpleNamespace(
        _synthetic_recovery_allowed=lambda: True,
        _fresh_synthesis_after_tool_loop=lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        _compose_turn_events=_compose_turn_events,
    )

    handler = build_terminal_handler(planner=planner, attachments=None)
    intent = handler(
        "请总结",
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={"command": "git status"},
            )
        ],
        [],
        None,
        None,
    )

    assert intent.status_hint == "degraded"
    assert intent.protocol_diagnostics["turn_terminal_state"]["reason"] == "final_synthesis_error"
    assert intent.protocol_diagnostics["turn_terminal_state"]["error_message"] == "RuntimeError: boom"
    assert intent.turn_events[-1] == {
        "type": "turn.failed",
        "error": {"message": "RuntimeError: boom"},
    }
    assert "回答阶段错误：RuntimeError: boom" in intent.assistant_text


def test_build_terminal_handler_surfaces_initial_send_error_without_extra_synthesis() -> None:
    planner = SimpleNamespace(
        _synthetic_recovery_allowed=lambda: True,
        _fresh_synthesis_after_tool_loop=lambda **_: (_ for _ in ()).throw(AssertionError("unused")),
        _compose_turn_events=_compose_turn_events,
    )

    handler = build_terminal_handler(planner=planner, attachments=None)
    intent = handler(
        "请总结",
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={"command": "python3 helloworld.py", "stdout": "Hello, world!\n"},
            )
        ],
        [],
        None,
        None,
        initial_send_error=RuntimeError("provider 503"),
    )

    assert intent.status_hint == "degraded"
    assert intent.protocol_diagnostics["turn_terminal_state"]["reason"] == "final_synthesis_error"
    assert "工具输出：\nHello, world!" in intent.assistant_text
    assert "回答阶段错误：RuntimeError: provider 503" in intent.assistant_text


def test_app_server_completed_turn_status_prefers_failed_terminal_state() -> None:
    response = PromptResponse(
        user_text="summarize",
        assistant_text="工具已执行完成，但回答阶段未产出可展示内容。",
        status={
            "terminal_state": "failed",
            "error": "工具已执行完成，但最终回答阶段未产出可展示内容。",
        },
        protocol_diagnostics={
            "turn_terminal_state": {
                "result": "failed",
                "reason": "final_answer_missing",
                "error_message": "工具已执行完成，但最终回答阶段未产出可展示内容。",
            }
        },
        tool_events=[ToolEvent(name="exec_command", ok=True, summary="exec_command exited", payload={"command": "pwd"})],
    )

    assert completed_turn_status(response) == "failed"
    assert turn_error_message(response) == "工具已执行完成，但最终回答阶段未产出可展示内容。"


def test_headless_exit_code_is_non_zero_for_failed_terminal_state() -> None:
    response = PromptResponse(
        user_text="summarize",
        assistant_text="工具已执行完成，但回答阶段未产出可展示内容。",
        status={
            "terminal_state": "failed",
            "error": "工具已执行完成，但最终回答阶段未产出可展示内容。",
        },
        protocol_diagnostics={
            "turn_terminal_state": {
                "result": "failed",
                "reason": "final_answer_missing",
                "error_message": "工具已执行完成，但最终回答阶段未产出可展示内容。",
            }
        },
        tool_events=[ToolEvent(name="exec_command", ok=True, summary="exec_command exited", payload={"command": "pwd"})],
    )

    assert exit_code_for_response(response, tool_event_is_soft_failure_fn=lambda _: False) == 2
