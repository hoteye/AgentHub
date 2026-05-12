from __future__ import annotations

from typing import Any, Dict, List


def stripped_optional_str(value: Any) -> str | None:
    return str(value or "").strip() or None


def timing_int(timings: Dict[str, Any], key: str) -> int:
    try:
        return int(timings.get(key) or 0)
    except Exception:
        return 0


def timing_list(timings: Dict[str, Any], key: str) -> List[Any]:
    value = timings.get(key)
    return list(value) if isinstance(value, list) else []


def merge_native_tool_timings(
    *,
    raw_timings: Dict[str, Any],
    synthesis_timings: Dict[str, Any],
    total_elapsed_ms: int,
    tool_call_count: int,
) -> Dict[str, Any]:
    merged = dict(raw_timings)
    for key, value in synthesis_timings.items():
        if key not in merged:
            merged[key] = value

    initial_model_ms = timing_int(raw_timings, "initial_model_ms") + timing_int(
        synthesis_timings, "initial_model_ms"
    )
    tool_execution_ms = timing_int(raw_timings, "tool_execution_ms") + timing_int(
        synthesis_timings, "tool_execution_ms"
    )
    synthesis_model_ms = timing_int(raw_timings, "synthesis_model_ms") + timing_int(
        synthesis_timings, "synthesis_model_ms"
    )
    planning_rounds = timing_int(raw_timings, "planning_rounds") + timing_int(
        synthesis_timings, "planning_rounds"
    )
    synthesis_rounds = timing_int(raw_timings, "synthesis_rounds") + timing_int(
        synthesis_timings, "synthesis_rounds"
    )
    planning_trace = timing_list(raw_timings, "planning_trace") + timing_list(
        synthesis_timings, "planning_trace"
    )
    synthesis_trace = timing_list(raw_timings, "synthesis_trace") + timing_list(
        synthesis_timings, "synthesis_trace"
    )
    computed_tool_call_count = max(
        timing_int(raw_timings, "tool_call_count"),
        timing_int(synthesis_timings, "tool_call_count"),
        int(tool_call_count),
    )
    accounted_ms = initial_model_ms + tool_execution_ms + synthesis_model_ms
    effective_total_ms = max(
        int(total_elapsed_ms),
        timing_int(raw_timings, "total_ms"),
        timing_int(synthesis_timings, "total_ms"),
        accounted_ms,
    )

    merged.update(
        {
            "initial_model_ms": initial_model_ms,
            "tool_execution_ms": tool_execution_ms,
            "synthesis_model_ms": synthesis_model_ms,
            "total_ms": effective_total_ms,
            "planning_rounds": planning_rounds,
            "synthesis_rounds": synthesis_rounds,
            "planning_trace": planning_trace,
            "synthesis_trace": synthesis_trace,
            "tool_call_count": computed_tool_call_count,
        }
    )
    return merged


def native_tool_loop_needs_synthesis(
    *,
    assistant_text: str,
    tool_events: List[Any] | None,
    tool_item_events: List[Dict[str, Any]],
    response_has_text: bool,
) -> bool:
    return not assistant_text and bool(tool_events) and not (tool_item_events and response_has_text)


def planning_only_timings(*, initial_model_ms: int, total_elapsed_ms: int) -> Dict[str, int]:
    return {
        "initial_model_ms": int(initial_model_ms),
        "tool_execution_ms": 0,
        "synthesis_model_ms": 0,
        "total_ms": int(total_elapsed_ms),
        "planning_rounds": 1,
        "synthesis_rounds": 0,
        "tool_call_count": 0,
    }


def stream_text_request_kwargs(
    *,
    model: str,
    instructions: str,
    input_items: List[Dict[str, Any]],
    reasoning: Any,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input_items,
        "store": False,
        "stream": True,
    }
    if reasoning:
        kwargs["reasoning"] = reasoning
    return kwargs


__all__ = [
    "merge_native_tool_timings",
    "native_tool_loop_needs_synthesis",
    "planning_only_timings",
    "stream_text_request_kwargs",
    "stripped_optional_str",
    "timing_int",
    "timing_list",
]
