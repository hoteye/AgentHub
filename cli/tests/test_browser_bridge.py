from __future__ import annotations

from cli.agent_cli.tools_core.browser_bridge import browser_action_result


def test_browser_action_result_records_event_and_items() -> None:
    payload = {"ok": True, "action": "act", "profile": "review", "target_id": "tab1"}
    result = browser_action_result(
        action="act",
        payload=payload,
        arguments={"profile": "fallback"},
    )

    assert result.tool_events[0].name == "browser_action"
    assert result.tool_events[0].summary == "act"
    assert result.tool_events[0].payload["profile"] == "review"
    assert result.tool_events[0].payload["target_id"] == "tab1"

    assert result.item_events[-1]["item"]["tool"] == "browser"
    assert result.item_events[-1]["item"]["arguments"]["action"] == "act"
    assert result.item_events[-1]["item"]["arguments"]["profile"] == "fallback"
    assert result.item_events[-1]["item"]["result"]["structured_content"]["target_id"] == "tab1"


def test_browser_action_result_maps_status_name() -> None:
    payload = {"ok": True, "status": "active", "profile": "user"}
    result = browser_action_result(action="status", payload=payload)

    assert result.tool_events[0].name == "browser_status"
    assert result.tool_events[0].summary == "active"
    assert result.item_events[-1]["item"]["arguments"]["action"] == "status"


def test_browser_action_result_handles_failure() -> None:
    payload = {"ok": False, "error": "timeout"}
    result = browser_action_result(action="download", payload=payload)

    assert result.tool_events[0].name == "browser_download"
    assert result.tool_events[0].ok is False
    assert result.item_events[-1]["item"]["status"] == "failed"
