from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.core.turn_engine_tool_runtime_helpers import run_tool_executor_structured
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.tool_call_context_runtime import current_provider_tool_call_id


def test_run_tool_executor_structured_sets_provider_call_id_for_structured_runner() -> None:
    captured: dict[str, object] = {}

    class _StructuredExecutor:
        def run_structured(self, command_text: str) -> CommandExecutionResult:
            captured["command_text"] = command_text
            captured["provider_call_id"] = current_provider_tool_call_id()
            return CommandExecutionResult(
                assistant_text="ok",
                tool_events=[ToolEvent(name="exec_command", ok=True, summary="ok", payload={})],
                item_events=[],
            )

    engine = SimpleNamespace(tool_executor=_StructuredExecutor())
    call = SimpleNamespace(call_id="call_exec_123", name="exec_command")

    result = run_tool_executor_structured(
        engine,
        call=call,
        command_text="/exec_command 'pwd'",
    )

    assert result.assistant_text == "ok"
    assert captured == {
        "command_text": "/exec_command 'pwd'",
        "provider_call_id": "call_exec_123",
    }


def test_run_tool_executor_structured_sets_provider_call_id_for_compat_runner() -> None:
    captured: dict[str, object] = {}

    def _compat_executor(command_text: str):
        captured["command_text"] = command_text
        captured["provider_call_id"] = current_provider_tool_call_id()
        return (
            "ok",
            [ToolEvent(name="exec_command", ok=True, summary="ok", payload={})],
        )

    engine = SimpleNamespace(tool_executor=_compat_executor)
    call = SimpleNamespace(call_id="call_exec_compat_1", name="exec_command")

    result = run_tool_executor_structured(
        engine,
        call=call,
        command_text="/exec_command 'ls'",
    )

    assert result.assistant_text == "ok"
    assert captured == {
        "command_text": "/exec_command 'ls'",
        "provider_call_id": "call_exec_compat_1",
    }
