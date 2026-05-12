from __future__ import annotations

from cli.agent_cli.core.turn_engine_tool_runtime import fallback_intent
from cli.agent_cli.models import AgentIntent, ToolEvent


def test_fallback_intent_merges_initial_model_ms_from_fallback_timings() -> None:
    event = ToolEvent(name="read_file", ok=True, summary="loaded", payload={"path": "README.md"})
    fallback = AgentIntent(
        assistant_text="fallback",
        status_hint="tool",
        tool_events=[event],
        timings={
            "initial_model_ms": 13,
            "tool_execution_ms": 5,
            "synthesis_model_ms": 7,
            "synthesis_rounds": 1,
        },
    )

    intent = fallback_intent(
        fallback,
        executed_events=[event],
        executed_item_events=[],
        model_ms=17,
        tool_execution_ms=19,
        planning_rounds=2,
        total_ms=10,
    )

    assert intent.timings["initial_model_ms"] == 30
    assert intent.timings["tool_execution_ms"] == 24
    assert intent.timings["synthesis_model_ms"] == 7
    assert intent.timings["total_ms"] == 61
