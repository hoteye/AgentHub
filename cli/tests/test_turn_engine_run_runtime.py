from __future__ import annotations

from cli.agent_cli.core.turn_engine_run_runtime import TurnEngineRunState, apply_tool_execution_results
from cli.agent_cli.core.turn_engine_tool_runtime import ToolExecutionResult
from cli.agent_cli.models import ResponseInputItem


def test_apply_tool_execution_results_prefers_prebuilt_output_items() -> None:
    output_item = {
        "id": "item_0",
        "type": "function_call_output",
        "call_id": "call_blocked_1",
        "output": "tool blocked",
        "success": False,
    }
    session_calls: list[dict[str, object]] = []
    emitted: list[dict[str, object]] = []
    state = TurnEngineRunState()

    class _Session:
        def build_tool_result_items(self, **kwargs):
            session_calls.append(dict(kwargs))
            return [{"type": "function_call_output", "call_id": "call_blocked_1", "output": "unexpected", "success": True}]

    tool_outputs, interrupted = apply_tool_execution_results(
        state=state,
        execution_results=[
            ToolExecutionResult(
                call_id="call_blocked_1",
                command_text="/exec_command 'blocked'",
                assistant_text="blocked",
                events=[],
                item_events=[{"type": "item.completed", "item": dict(output_item)}],
                elapsed_ms=7,
            )
        ],
        batch_execution_ms=7,
        emit_turn_events_fn=lambda events: emitted.extend(events),
        session=_Session(),
        interrupt_requested_fn=lambda: False,
        annotate_trace_with_orchestration_outcomes_fn=lambda *_args, **_kwargs: None,
    )

    assert interrupted is False
    assert session_calls == []
    assert emitted == [{"type": "item.completed", "item": dict(output_item)}]
    assert tool_outputs == [ResponseInputItem.from_dict(output_item).to_dict()]
    assert state.executed_events == []
    assert state.executed_item_events == [{"type": "item.completed", "item": dict(output_item)}]
    assert state.tool_execution_ms == 7
