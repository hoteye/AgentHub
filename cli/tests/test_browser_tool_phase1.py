from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.ui.transcript_formatting import format_browser_activity_lines
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolPhase1TranscriptTest(unittest.TestCase):
    def test_status_event_formatting(self) -> None:
        event = ToolEvent(
            name="browser_status",
            ok=True,
            summary="browser ok",
            payload={"profile": "openclaw", "running": True, "tabs": 2},
        )
        activities = activity_events_for_tool_event(event)
        self.assertEqual(len(activities), 1)
        activity = activities[0]
        self.assertEqual(activity.title, "Browser status")
        self.assertEqual(activity.kind, "browser")
        lines = format_browser_activity_lines(activity)
        self.assertTrue(any("profile=openclaw" in line for line in lines))
        self.assertTrue(any("tabs=2" in line for line in lines))

    def test_action_event_failure_detail(self) -> None:
        event = ToolEvent(
            name="browser_action",
            ok=False,
            summary="browser action fail",
            payload={"action": "click", "target_id": "tab-123"},
        )
        activities = activity_events_for_tool_event(event)
        activity = activities[0]
        self.assertEqual(activity.title, "Browser action failed")
        lines = format_browser_activity_lines(activity)
        self.assertTrue(any("action=click" in line for line in lines))
        self.assertTrue(any("target=tab-123" in line for line in lines))

    def test_console_event_lines(self) -> None:
        event = ToolEvent(
            name="browser_console",
            ok=True,
            summary="console output",
            payload={"level": "warn", "message": "popup blocked"},
        )
        activities = activity_events_for_tool_event(event)
        activity = activities[0]
        lines = format_browser_activity_lines(activity)
        self.assertTrue(any("level=warn" in line for line in lines))
        self.assertTrue(any("msg=popup blocked" in line for line in lines))

class BrowserToolPhase1ExecutionTest(unittest.TestCase):
    def test_tool_registry_browser_status_and_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    tools = ToolRegistry()

                    status_event = tools.browser("status")
                    self.assertEqual(status_event.name, "browser_status")
                    self.assertTrue(status_event.ok)
                    self.assertFalse(status_event.payload["running"])

                    start_event = tools.browser("start")
                    self.assertEqual(start_event.name, "browser_action")
                    self.assertTrue(start_event.ok)

                    next_status = tools.browser("status")
                    self.assertTrue(next_status.payload["running"])
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_command_open_and_navigate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    started = runtime.handle_prompt("/browser start")
                    self.assertEqual([item.name for item in started.tool_events], ["browser_action"])
                    self.assertTrue(started.tool_events[0].ok)

                    opened = runtime.handle_prompt("/browser open --url https://example.com")
                    self.assertEqual([item.name for item in opened.tool_events], ["browser_action"])
                    self.assertEqual(opened.tool_events[0].payload["action"], "open")
                    self.assertEqual(opened.tool_events[0].payload["url"], "https://example.com")

                    navigated = runtime.handle_prompt("/browser navigate --url https://example.com/docs")
                    self.assertEqual([item.name for item in navigated.tool_events], ["browser_action"])
                    self.assertEqual(navigated.tool_events[0].payload["action"], "navigate")
                    self.assertEqual(navigated.tool_events[0].payload["url"], "https://example.com/docs")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_browser_runtime_only_legacy_actions_are_semantically_equivalent_to_direct_web_aliases(self) -> None:
        tools = ToolRegistry()
        with patch("cli.agent_cli.tools_core.browser_web_runtime.web_tools_runtime.open") as open_mock, patch(
            "cli.agent_cli.tools_core.browser_web_runtime.web_tools_runtime.click"
        ) as click_mock, patch("cli.agent_cli.tools_core.browser_web_runtime.web_tools_runtime.find") as find_mock:
            open_mock.side_effect = lambda **kwargs: ToolEvent(
                name="open",
                ok=True,
                summary="page opened",
                payload={"ok": True, "ref": kwargs["ref"], "line": kwargs["line"]},
            )
            click_mock.side_effect = lambda **kwargs: ToolEvent(
                name="click",
                ok=True,
                summary="link opened",
                payload={"ok": True, "ref_id": kwargs["ref_id"], "id": kwargs["id"]},
            )
            find_mock.side_effect = lambda **kwargs: ToolEvent(
                name="find",
                ok=True,
                summary="matches=1",
                payload={"ok": True, "ref_id": kwargs["ref_id"], "pattern": kwargs["pattern"], "count": 1},
            )

            direct_open = tools.open("https://example.com/docs", line=2)
            legacy_open = tools.browser("open_legacy", ref="https://example.com/docs", line=2)
            self.assertEqual(legacy_open, direct_open)

            direct_open_default = tools.open("https://example.com/default")
            legacy_open_default = tools.browser("open_legacy", ref="https://example.com/default")
            self.assertEqual(legacy_open_default, direct_open_default)

            direct_click = tools.click("page_1", id=1)
            legacy_click = tools.browser("click_legacy", ref="page_1", id=1)
            self.assertEqual(legacy_click, direct_click)

            direct_find = tools.find("page_1", pattern="Responses API")
            legacy_find = tools.browser("find_legacy", ref="page_1", text="Responses API")
            self.assertEqual(legacy_find, direct_find)

            self.assertEqual(
                [(call.kwargs["ref"], call.kwargs["line"]) for call in open_mock.call_args_list],
                [
                    ("https://example.com/docs", 2),
                    ("https://example.com/docs", 2),
                    ("https://example.com/default", 1),
                    ("https://example.com/default", 1),
                ],
            )
            self.assertEqual(
                [(call.kwargs["ref_id"], call.kwargs["id"]) for call in click_mock.call_args_list],
                [("page_1", 1), ("page_1", 1)],
            )
            self.assertEqual(
                [(call.kwargs["ref_id"], call.kwargs["pattern"]) for call in find_mock.call_args_list],
                [("page_1", "Responses API"), ("page_1", "Responses API")],
            )

    def test_browser_runtime_only_legacy_actions_validate_required_args_payloads(self) -> None:
        tools = ToolRegistry()
        with patch("cli.agent_cli.tools_core.browser_web_runtime.web_tools_runtime.click") as click_mock, patch(
            "cli.agent_cli.tools_core.browser_web_runtime.web_tools_runtime.find"
        ) as find_mock:
            missing_click_id = tools.browser("click_legacy", ref="page_1")
            self.assertFalse(missing_click_id.ok)
            self.assertEqual(missing_click_id.name, "click")
            self.assertEqual(missing_click_id.summary, "click failed")
            self.assertEqual(
                missing_click_id.payload,
                {"ok": False, "error": "missing ref or id", "ref_id": "page_1", "id": None},
            )

            missing_click_ref = tools.browser("click_legacy", ref="", id=7)
            self.assertFalse(missing_click_ref.ok)
            self.assertEqual(missing_click_ref.name, "click")
            self.assertEqual(missing_click_ref.summary, "click failed")
            self.assertEqual(
                missing_click_ref.payload,
                {"ok": False, "error": "missing ref or id", "ref_id": "", "id": 7},
            )

            missing_find_pattern = tools.browser("find_legacy", ref="page_1", text="")
            self.assertFalse(missing_find_pattern.ok)
            self.assertEqual(missing_find_pattern.name, "find")
            self.assertEqual(missing_find_pattern.summary, "find failed")
            self.assertEqual(
                missing_find_pattern.payload,
                {"ok": False, "error": "missing ref or pattern", "ref_id": "page_1", "pattern": ""},
            )

            missing_find_ref = tools.browser("find_legacy", text="Responses API")
            self.assertFalse(missing_find_ref.ok)
            self.assertEqual(missing_find_ref.name, "find")
            self.assertEqual(missing_find_ref.summary, "find failed")
            self.assertEqual(
                missing_find_ref.payload,
                {"ok": False, "error": "missing ref or pattern", "ref_id": "", "pattern": "Responses API"},
            )

            click_mock.assert_not_called()
            find_mock.assert_not_called()
