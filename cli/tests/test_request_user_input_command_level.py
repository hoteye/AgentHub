from __future__ import annotations

import json
from types import SimpleNamespace

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.command_handlers import handle_known_command


def _runtime_stub(
    *,
    collaboration_mode: str = "default",
    default_mode_request_user_input: bool = False,
    request_user_input_handler=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        collaboration_mode=collaboration_mode,
        default_mode_request_user_input=default_mode_request_user_input,
        request_user_input_handler=request_user_input_handler,
        _is_interrupt_requested=lambda: False,
        _interrupt_tuple=lambda: ("interrupted", [ToolEvent(name="interrupt", ok=False, summary="interrupt", payload={})]),
    )


def _request_arg_text() -> str:
    return (
        '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
        '"options":[{"label":"Yes (Recommended)","description":"Continue."},'
        '{"label":"No","description":"Stop."}]}]}'
    )


def test_request_user_input_command_usage_without_arguments() -> None:
    runtime = _runtime_stub()
    result = handle_known_command(
        runtime,
        name="request_user_input",
        arg_text="",
        text="/request_user_input",
    )
    assert result is not None
    assert result.assistant_text.startswith("Usage: /request_user_input")
    assert result.tool_events == []


def test_request_user_input_command_rejected_in_default_mode_when_disabled() -> None:
    runtime = _runtime_stub(collaboration_mode="default", default_mode_request_user_input=False)
    result = handle_known_command(
        runtime,
        name="request_user_input",
        arg_text=_request_arg_text(),
        text=f"/request_user_input {_request_arg_text()}",
    )
    assert result is not None
    assert result.tool_events[0].name == "request_user_input"
    assert result.tool_events[0].ok is False
    assert "unavailable in Default mode" in result.assistant_text


def test_request_user_input_command_cancelled_when_handler_missing_in_plan_mode() -> None:
    runtime = _runtime_stub(collaboration_mode="plan")
    result = handle_known_command(
        runtime,
        name="request_user_input",
        arg_text=_request_arg_text(),
        text=f"/request_user_input {_request_arg_text()}",
    )
    assert result is not None
    assert result.tool_events[0].name == "request_user_input"
    assert result.tool_events[0].ok is False
    assert "cancelled before receiving a response" in result.assistant_text


def test_request_user_input_command_success_in_default_mode_when_enabled() -> None:
    runtime = _runtime_stub(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {"confirm_path": {"answers": ["Yes (Recommended)"]}},
        },
    )
    result = handle_known_command(
        runtime,
        name="request_user_input",
        arg_text=_request_arg_text(),
        text=f"/request_user_input {_request_arg_text()}",
    )
    assert result is not None
    assert result.tool_events[0].name == "request_user_input"
    assert result.tool_events[0].ok is True
    output_payload = json.loads(result.assistant_text)
    assert output_payload["answers"]["confirm_path"]["answers"] == ["Yes (Recommended)"]


def test_request_user_input_command_normalizes_non_canonical_handler_output() -> None:
    runtime = _runtime_stub(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {"confirm_path": "yes", "unknown_id": "ignored"},
        },
    )
    result = handle_known_command(
        runtime,
        name="request_user_input",
        arg_text=_request_arg_text(),
        text=f"/request_user_input {_request_arg_text()}",
    )
    assert result is not None
    payload = json.loads(result.assistant_text)
    assert payload["answers"]["confirm_path"]["answers"] == ["yes"]
    assert "unknown_id" not in payload["answers"]
