from __future__ import annotations

from dataclasses import replace

from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.runtime_core import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_history import activity_entry, render_transcript_visual_entries


def test_web_search_activity_entry_uses_dedicated_render_mode() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched the web",
            status="success",
            kind="web",
            code="web.search",
            detail="query=openai responses api weather routing",
        )
    )

    assert entry is not None
    assert entry.layer == "web"
    assert entry.render_mode == "web_search"
    assert entry.structured is not None
    assert entry.structured["type"] == "activity"
    assert entry.structured["name"] == "web.search"
    assert entry.structured["state"] == "completed"
    assert entry.structured["output"] == "query=openai responses api weather routing"
    assert entry.lines == [
        "• Searched the web",
        "  └ openai responses api weather routing",
    ]


def test_web_search_visual_render_wraps_query_with_tree_prefix_consistently() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched the web",
            status="success",
            kind="web",
            code="web.search",
            detail="query=openai responses api weather routing",
        )
    )

    assert entry is not None
    rendered = render_transcript_visual_entries([entry], width=24)

    assert rendered.lines == [
        "⌕ Searched the web",
        "  └ openai responses api",
        "    weather routing",
    ]


def test_web_search_visual_render_uses_structured_block_before_legacy_lines() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Native web search",
            status="success",
            kind="web",
            code="web.search",
            detail="query=北京 明天天气\ncount=1",
            params={"query": "北京 明天天气", "backend": "native", "count": 1},
        )
    )

    assert entry is not None
    tampered = replace(entry, lines=["BROKEN LEGACY LINE"])
    rendered = render_transcript_visual_entries([tampered], width=80)

    assert rendered.lines == [
        "⌕ Native web search",
        "  │ state: search_results_received",
        "  │ backend: native",
        "  │ count: 1",
        "  └ 北京 明天天气",
    ]


def test_non_search_web_activity_keeps_plain_render_mode() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Opened webpage",
            status="success",
            kind="web",
            code="web.open",
            detail="page_1 | platform.openai.com | OpenAI API docs",
        )
    )

    assert entry is not None
    assert entry.render_mode == "plain"
    assert entry.lines == [
        "• Opened webpage",
        "  └ OpenAI API docs",
    ]


def test_native_web_search_activity_entry_labels_backend_explicitly() -> None:
    event = ToolEvent(
        name="web_search",
        ok=True,
        summary="web results=1",
        payload={
            "query": "北京 明天天气",
            "count": 1,
            "engine": "openai_native_web_search",
            "web_search_route": {
                "effective_backend_id": "provider_native_openai_responses_web_search",
                "effective_backend_kind": "provider_native",
                "execution_path": "openai_responses_native",
            },
        },
    )

    activity = activity_events_for_tool_event(event)[0]
    entry = activity_entry(activity)

    assert activity.title == "Native web search"
    assert entry is not None
    assert entry.render_mode == "web_search"
    assert entry.lines == [
        "Native web search",
        "  └ 北京 明天天气",
        "    state=search_results_received | backend=native | count=1",
    ]


def test_local_web_search_activity_entry_labels_backend_explicitly() -> None:
    event = ToolEvent(
        name="web_search",
        ok=True,
        summary="web results=1",
        payload={
            "query": "rg 怎么用",
            "count": 1,
            "engine": "local_web_search",
            "web_search_route": {
                "effective_backend_id": "local_web_search",
                "effective_backend_kind": "local_fallback",
                "execution_path": "local_fallback",
            },
        },
    )

    activity = activity_events_for_tool_event(event)[0]
    entry = activity_entry(activity)

    assert activity.title == "Local web search"
    assert entry is not None
    assert entry.render_mode == "web_search"
    assert entry.lines == [
        "Local web search",
        "  └ rg 怎么用",
        "    state=search_results_received | backend=local | count=1",
    ]


def test_native_web_search_activity_entry_surfaces_interrupted_state_compactly() -> None:
    event = ToolEvent(
        name="web_search",
        ok=False,
        summary="web search interrupted",
        payload={
            "query": "北京 明天天气",
            "count": 0,
            "engine": "openai_native_web_search",
            "error": "native web search response was incomplete before usable results were received",
            "web_search_route": {
                "effective_backend_id": "provider_native_openai_responses_web_search",
                "effective_backend_kind": "provider_native",
                "execution_path": "openai_responses_native",
            },
        },
    )

    activity = activity_events_for_tool_event(event)[0]
    entry = activity_entry(activity)

    assert activity.title == "Native web search failed"
    assert entry is not None
    assert entry.render_mode == "web_search"
    assert entry.lines == [
        "Native web search failed",
        "  └ 北京 明天天气",
        "    state=native_interrupted | backend=native",
        "    reason=native web search response was incomplete before usable results were received",
    ]


def test_web_search_activity_entry_prefers_explicit_outcome_param_over_detail_heuristics() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Native web search failed",
            status="error",
            kind="web",
            code="web.search",
            detail="query=北京 明天天气\nnative request failed in an unexpected way",
            params={
                "query": "北京 明天天气",
                "backend": "native",
                "web_search_outcome": "provider_error_without_search",
            },
        )
    )

    assert entry is not None
    assert entry.lines == [
        "Native web search failed",
        "  └ 北京 明天天气",
        "    state=provider_error_without_search | backend=native",
        "    reason=native request failed in an unexpected way",
    ]
