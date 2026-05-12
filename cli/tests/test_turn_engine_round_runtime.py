from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.core.turn_engine_round_runtime import (
    build_trace_entry,
    next_round_input_items,
    record_tool_call_round_items,
    resolve_terminal_round,
)
from cli.agent_cli.models import AgentIntent, ToolEvent, response_message_item

def test_build_trace_entry_uses_response_output_for_terminal_answer_preview() -> None:
    step = SimpleNamespace(
        output_text="final answer",
        tool_calls=[],
        response_items=[response_message_item("assistant", "final answer", phase="final_answer")],
        trace={},
    )

    trace = build_trace_entry(
        planning_round=2,
        request_elapsed_ms=17,
        step=step,
        summary_builder=lambda tool_calls: {"delegation_decision": "none", "count": len(tool_calls)},
    )

    assert trace == {
        "round": 2,
        "model_ms": 17,
        "tool_calls": [],
        "tool_call_count": 0,
        "answered": True,
        "answer_preview": "final answer",
        "delegation_decision": "none",
        "count": 0,
    }

def test_record_tool_call_round_items_adds_synthetic_preamble_when_provider_did_not_stream_message() -> None:
    step = SimpleNamespace(
        tool_calls=[SimpleNamespace(name="list_dir", arguments={"dir_path": "."})],
        response_items=[],
        trace={},
    )
    executed_item_events = []
    emitted = []

    record_tool_call_round_items(
        step=step,
        executed_item_events=executed_item_events,
        emit_turn_event=emitted.append,
        preamble_text_builder=lambda name, arguments: f"{name}:{arguments['dir_path']}",
        synthetic_event_builder=lambda *, item_id, text: {
            "type": "item.completed",
            "item": {"id": item_id, "type": "agent_message", "text": text},
        },
    )

    assert executed_item_events == emitted
    assert executed_item_events == [
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": "list_dir:."},
        }
    ]


def test_record_tool_call_round_items_skips_duplicate_synthetic_preamble() -> None:
    step = SimpleNamespace(
        tool_calls=[SimpleNamespace(name="list_dir", arguments={"dir_path": "."})],
        response_items=[],
        trace={},
    )
    executed_item_events = [
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": "list_dir:."},
        },
        {
            "type": "item.started",
            "item": {"id": "item_1", "type": "command_execution"},
        },
        {
            "type": "item.completed",
            "item": {"id": "item_1", "type": "command_execution"},
        },
    ]
    emitted = []

    record_tool_call_round_items(
        step=step,
        executed_item_events=executed_item_events,
        emit_turn_event=emitted.append,
        preamble_text_builder=lambda name, arguments: f"{name}:{arguments['dir_path']}",
        synthetic_event_builder=lambda *, item_id, text: {
            "type": "item.completed",
            "item": {"id": item_id, "type": "agent_message", "text": text},
        },
    )

    assert emitted == []
    assert executed_item_events == [
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": "list_dir:."},
        },
        {
            "type": "item.started",
            "item": {"id": "item_1", "type": "command_execution"},
        },
        {
            "type": "item.completed",
            "item": {"id": "item_1", "type": "command_execution"},
        },
    ]


def test_resolve_terminal_round_uses_terminal_handler_for_empty_output() -> None:
    step = SimpleNamespace(output_text="", tool_calls=[], response_items=[], trace={})
    expected_intent = AgentIntent(assistant_text="fallback", status_hint="tool")

    resolution = resolve_terminal_round(
        step=step,
        interrupt_requested=False,
        fallback_on_empty_output=True,
        executed_events=[ToolEvent(name="read_file", ok=True, summary="loaded", payload={"path": "README.md"})],
        executed_item_events=[],
        terminal_handler=lambda *_args: expected_intent,
        user_text="read",
        previous_response_id="resp_1",
        continuation_input_items=[{"type": "function_call_output", "call_id": "c1", "output": "ok"}],
        model_ms=20,
        tool_execution_ms=5,
        planning_rounds=1,
        planning_trace=[],
        total_ms_builder=lambda: 30,
        interrupted_intent_builder=lambda: AgentIntent(assistant_text="interrupted"),
        final_intent_builder=lambda **kwargs: AgentIntent(assistant_text=str(kwargs["assistant_text"])),
        handler_invoker=lambda handler, **kwargs: handler(kwargs["user_text"], kwargs["executed_events"]),
        fallback_intent_builder=lambda fallback, **_kwargs: fallback,
        fallback_text_builder=lambda _events: "fallback text",
    )

    assert resolution is not None
    assert resolution.intent is expected_intent


def test_resolve_terminal_round_skips_terminal_when_provider_native_continuation_pending() -> None:
    step = SimpleNamespace(
        output_text="我来查一下北京今天的天气。",
        tool_calls=[],
        response_items=[],
        trace={"provider_native_continuation_pending": True},
    )

    resolution = resolve_terminal_round(
        step=step,
        interrupt_requested=False,
        fallback_on_empty_output=True,
        executed_events=[],
        executed_item_events=[],
        terminal_handler=lambda *_args: AgentIntent(assistant_text="fallback"),
        user_text="weather",
        previous_response_id="resp_partial",
        continuation_input_items=[
            {"role": "user", "content": "北京今天天气怎么样？"},
            {"type": "web_search_call", "status": "completed"},
        ],
        model_ms=20,
        tool_execution_ms=0,
        planning_rounds=1,
        planning_trace=[],
        total_ms_builder=lambda: 30,
        interrupted_intent_builder=lambda: AgentIntent(assistant_text="interrupted"),
        final_intent_builder=lambda **kwargs: AgentIntent(assistant_text=str(kwargs["assistant_text"])),
        handler_invoker=lambda handler, **kwargs: handler(kwargs["user_text"], kwargs["executed_events"]),
        fallback_intent_builder=lambda fallback, **_kwargs: fallback,
        fallback_text_builder=lambda _events: "fallback text",
    )

    assert resolution is None


def test_resolve_terminal_round_computes_total_ms_after_terminal_handler() -> None:
    step = SimpleNamespace(output_text="", tool_calls=[], response_items=[], trace={})
    expected_intent = AgentIntent(assistant_text="fallback", status_hint="tool")
    state = {"handler_invoked": False}
    observed: dict[str, int] = {}

    def _total_ms_builder() -> int:
        return 88 if state["handler_invoked"] else 12

    def _handler_invoker(handler, **kwargs):
        state["handler_invoked"] = True
        return handler(kwargs["user_text"], kwargs["executed_events"])

    def _fallback_intent_builder(fallback, **kwargs):
        observed["total_ms"] = int(kwargs["total_ms"])
        return fallback

    resolution = resolve_terminal_round(
        step=step,
        interrupt_requested=False,
        fallback_on_empty_output=True,
        executed_events=[ToolEvent(name="read_file", ok=True, summary="loaded", payload={"path": "README.md"})],
        executed_item_events=[],
        terminal_handler=lambda *_args: expected_intent,
        user_text="read",
        previous_response_id="resp_1",
        continuation_input_items=[{"type": "function_call_output", "call_id": "c1", "output": "ok"}],
        model_ms=20,
        tool_execution_ms=5,
        planning_rounds=1,
        planning_trace=[],
        total_ms_builder=_total_ms_builder,
        interrupted_intent_builder=lambda: AgentIntent(assistant_text="interrupted"),
        final_intent_builder=lambda **kwargs: AgentIntent(assistant_text=str(kwargs["assistant_text"])),
        handler_invoker=_handler_invoker,
        fallback_intent_builder=_fallback_intent_builder,
        fallback_text_builder=lambda _events: "fallback text",
    )

    assert resolution is not None
    assert resolution.intent is expected_intent
    assert observed["total_ms"] == 88


def test_next_round_input_items_uses_incremental_delta_for_local_tool_followup() -> None:
    items = next_round_input_items(
        continuation_input_items=[
            {"type": "message", "role": "user", "content": "hello"},
            {"type": "function_call", "call_id": "c1", "name": "list_dir", "arguments": "{}"},
        ],
        tool_outputs=[
            {"type": "function_call_output", "call_id": "c1", "output": "ok", "success": True},
        ],
        incremental_continuation=True,
    )

    assert items == [
        {"type": "function_call_output", "call_id": "c1", "output": "ok", "success": True},
    ]


def test_next_round_input_items_keeps_provider_native_continuation_items() -> None:
    items = next_round_input_items(
        continuation_input_items=[
            {"role": "user", "content": "北京今天天气怎么样？"},
            {"type": "web_search_call", "status": "completed"},
        ],
        tool_outputs=[],
        incremental_continuation=False,
    )

    assert items == [
        {"role": "user", "content": "北京今天天气怎么样？"},
        {"type": "web_search_call", "status": "completed"},
    ]
