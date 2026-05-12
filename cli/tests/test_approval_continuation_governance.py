from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from cli.agent_cli.core.provider_session import ProviderSession, ProviderSessionResult, ProviderToolCall
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import (
    AgentIntent,
    ToolEvent,
    compose_turn_events_from_response_items,
    generic_tool_call_item_events,
    response_items_with_tool_outputs,
    shell_tool_call_item_events,
)
from cli.agent_cli.providers.openai_planner_runtime_helpers_runtime import build_terminal_handler
from cli.agent_cli.providers.openai_planner_runtime_projection_helpers_runtime import fallback_tool_intent
from cli.agent_cli.runtime import AgentCliRuntime

from tests.test_runtime_policy import _PolicyAgent, _PolicyTools


class _GovernanceSession(ProviderSession):
    def __init__(self, scripted: List[ProviderSessionResult | Exception]) -> None:
        self.scripted = list(scripted)
        self.calls: List[Dict[str, Any]] = []

    def send(
        self,
        *,
        input_items: List[Dict[str, Any]],
        allow_tools: bool,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input_items": list(input_items),
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        if not self.scripted:
            raise RuntimeError("no scripted response")
        result = self.scripted.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _compose_turn_events(*, assistant_text: str, response_items: list[Any], executed_item_events: list[dict[str, Any]]):
    return compose_turn_events_from_response_items(
        assistant_text=assistant_text,
        response_items=list(response_items or []),
        executed_item_events=list(executed_item_events or []),
    )


def _governance_terminal_handler():
    planner = SimpleNamespace(
        _synthetic_recovery_allowed=lambda: True,
        _fresh_synthesis_after_tool_loop=lambda **_: (_ for _ in ()).throw(AssertionError("unused")),
        _compose_turn_events=_compose_turn_events,
    )
    return build_terminal_handler(planner=planner, attachments=None)


def test_rule_1_exec_command_and_shell_start_approval_modes_do_not_cross() -> None:
    exec_tools = _PolicyTools()
    exec_runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=exec_tools)
    exec_request = exec_runtime.handle_prompt("/exec_command 'python -V'")
    exec_approval = exec_request.tool_events[0]
    exec_decision = exec_runtime.handle_prompt(f"/approve {exec_approval.payload['approval_id']}")

    assert exec_approval.payload["exec_mode"] == "exec_once"
    assert [event.name for event in exec_decision.tool_events] == ["approval_decision", "shell"]
    assert exec_tools.shell_calls == ["python -V"]
    assert exec_tools.shell_start_calls == []

    session_tools = _PolicyTools()
    session_runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=session_tools)
    session_request = session_runtime.handle_prompt("/shell start python -i")
    session_approval = session_request.tool_events[0]
    session_decision = session_runtime.handle_prompt(f"/approve {session_approval.payload['approval_id']}")

    assert session_approval.payload["exec_mode"] == "session_start"
    assert [event.name for event in session_decision.tool_events] == ["approval_decision", "shell_start"]
    assert session_tools.shell_calls == []
    assert session_tools.shell_start_calls == ["python -i"]


def test_rule_2_rescue_continuation_failure_keeps_all_executed_tools() -> None:
    send_error = RuntimeError("provider 503")
    initial_event = ToolEvent(
        name="exec_command",
        ok=True,
        summary="exec_command exited",
        payload={
            "command": "rg --files -g helloworld.py",
            "stdout": "helloworld.py\n",
            "returncode": 0,
            "provider_call_id": "call_rg",
        },
    )
    session = _GovernanceSession(
        [
            ProviderSessionResult(
                output_text="",
                tool_calls=[
                    ProviderToolCall(
                        call_id="call_patch",
                        name="apply_patch",
                        arguments={
                            "patch": "*** Begin Patch\n*** Add File: helloworld.py\n+print('hi')\n*** End Patch"
                        },
                    )
                ],
                response_id="resp_patch",
            ),
            send_error,
        ]
    )

    def tool_executor(_command_text: str):
        return "patch applied", [
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="apply_patch files=1",
                payload={"file_count": 1, "changes": [{"path": "helloworld.py", "change_type": "add"}]},
            )
        ]

    engine = TurnEngine(
        session,
        tool_executor=tool_executor,
        command_builder=lambda name, _arguments: f"/{name}",
        terminal_handler=_governance_terminal_handler(),
    )
    intent = engine.run(
        user_text="create file",
        initial_input=[{"role": "user", "content": "create file"}],
        initial_previous_response_id="resp_rg",
        initial_executed_events=[initial_event],
        initial_executed_item_events=shell_tool_call_item_events(initial_event, command="rg --files -g helloworld.py"),
    )

    assert [event.name for event in intent.tool_events] == ["exec_command", "apply_patch"]
    assert intent.status_hint == "tool"
    assert "回答阶段错误：RuntimeError: provider 503" in intent.assistant_text
    assert intent.turn_events[-1]["type"] == "turn.failed"


def test_rule_3_fallback_projection_preserves_replayable_tool_ledger() -> None:
    shell_event = ToolEvent(
        name="exec_command",
        ok=True,
        summary="exec_command exited",
        payload={
            "command": "rg --files -g helloworld.py",
            "stdout": "helloworld.py\n",
            "returncode": 0,
            "provider_call_id": "call_rg",
        },
    )
    patch_event = ToolEvent(
        name="apply_patch",
        ok=True,
        summary="apply_patch files=1",
        payload={
            "provider_call_id": "call_patch",
            "function_call_arguments": {"patch": "*** Begin Patch\n*** End Patch"},
            "file_count": 1,
        },
    )
    executed_item_events = shell_tool_call_item_events(shell_event, command="rg --files -g helloworld.py")
    executed_item_events.extend(
        generic_tool_call_item_events(
            tool_name="apply_patch",
            arguments={"patch": "*** Begin Patch\n*** End Patch"},
            ok=True,
            summary="apply_patch files=1",
            structured_content=dict(patch_event.payload),
            item_id="item_3",
        )
    )

    intent: AgentIntent = fallback_tool_intent(
        executed_events=[shell_event, patch_event],
        executed_item_events=executed_item_events,
        compose_turn_events_fn=_compose_turn_events,
        failure_reason="final_synthesis_error",
        failure_message="RuntimeError: provider 503",
    )
    completed_items = [
        dict(event.get("item") or {})
        for event in intent.turn_events
        if str(event.get("type") or "") == "item.completed"
    ]
    replay_items = response_items_with_tool_outputs(intent.response_items, intent.turn_events, intent.tool_events)

    assert [event.name for event in intent.tool_events] == ["exec_command", "apply_patch"]
    assert any(item.get("type") == "command_execution" and item.get("call_id") == "call_rg" for item in completed_items)
    assert any(item.get("type") == "mcp_tool_call" and item.get("call_id") == "call_patch" for item in completed_items)
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "call_rg" for item in replay_items)
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "call_patch" for item in replay_items)
    assert intent.turn_events[-1]["type"] == "turn.failed"
