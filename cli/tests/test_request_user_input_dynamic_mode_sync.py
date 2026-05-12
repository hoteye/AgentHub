from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import runtime as runtime_module
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.command_handlers import handle_known_command


def _request_arg_text() -> str:
    return (
        '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
        '"options":[{"label":"Yes (Recommended)","description":"Continue."},'
        '{"label":"No","description":"Stop."}]}]}'
    )


def _request_command_text() -> str:
    return f"/request_user_input {_request_arg_text()}"


def _build_runtime(*, default_mode_enabled: bool, request_user_input_handler) -> SimpleNamespace:
    planner_config = SimpleNamespace(
        raw_model={"default_mode_request_user_input": default_mode_enabled},
        raw_provider={},
    )
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=False,
        request_user_input_handler=request_user_input_handler,
        _is_interrupt_requested=lambda: False,
        _interrupt_tuple=lambda: (
            "interrupted",
            [ToolEvent(name="interrupt", ok=False, summary="interrupt", payload={})],
        ),
        agent=SimpleNamespace(_planner=SimpleNamespace(config=planner_config)),
    )

    def _sync() -> bool:
        return runtime_module.sync_runtime_request_user_input_mode(runtime)

    runtime._sync_request_user_input_mode_from_provider = _sync
    return runtime


def _dispatch_known_request_command(runtime, text: str):
    prefix = "/request_user_input "
    assert text.startswith(prefix)
    return handle_known_command(
        runtime,
        name="request_user_input",
        arg_text=text[len(prefix) :],
        text=text,
    )


def test_dynamic_mode_sync_enables_request_user_input_after_provider_flag_turns_on() -> None:
    runtime = _build_runtime(
        default_mode_enabled=False,
        request_user_input_handler=lambda _payload: {
            "answers": {"confirm_path": {"answers": ["Yes (Recommended)"]}},
        },
    )
    with patch.object(runtime_module, "_ORIGINAL_RUN_COMMAND_TEXT_RESULT", _dispatch_known_request_command):
        disabled_result = runtime_module._run_command_text_result_with_request_user_input_sync(
            runtime,
            _request_command_text(),
        )

        assert runtime.default_mode_request_user_input is False
        assert disabled_result is not None
        assert disabled_result.tool_events[0].ok is False
        assert "unavailable in Default mode" in disabled_result.assistant_text

        runtime.agent._planner.config.raw_model["default_mode_request_user_input"] = True
        enabled_result = runtime_module._run_command_text_result_with_request_user_input_sync(
            runtime,
            _request_command_text(),
        )

    assert runtime.default_mode_request_user_input is True
    assert enabled_result is not None
    assert enabled_result.tool_events[0].ok is True
    payload = json.loads(enabled_result.assistant_text)
    assert payload["answers"]["confirm_path"]["answers"] == ["Yes (Recommended)"]


def test_dynamic_mode_sync_disables_request_user_input_and_blocks_subsequent_request() -> None:
    call_counter = {"count": 0}

    def _handler(_payload):
        call_counter["count"] += 1
        return {"answers": {"confirm_path": {"answers": ["Yes (Recommended)"]}}}

    runtime = _build_runtime(
        default_mode_enabled=True,
        request_user_input_handler=_handler,
    )
    with patch.object(runtime_module, "_ORIGINAL_RUN_COMMAND_TEXT_RESULT", _dispatch_known_request_command):
        enabled_result = runtime_module._run_command_text_result_with_request_user_input_sync(
            runtime,
            _request_command_text(),
        )

        assert runtime.default_mode_request_user_input is True
        assert enabled_result is not None
        assert enabled_result.tool_events[0].ok is True
        assert call_counter["count"] == 1

        runtime.agent._planner.config.raw_model["default_mode_request_user_input"] = False
        disabled_result = runtime_module._run_command_text_result_with_request_user_input_sync(
            runtime,
            _request_command_text(),
        )

    assert runtime.default_mode_request_user_input is False
    assert disabled_result is not None
    assert disabled_result.tool_events[0].ok is False
    assert "unavailable in Default mode" in disabled_result.assistant_text
    assert call_counter["count"] == 1
