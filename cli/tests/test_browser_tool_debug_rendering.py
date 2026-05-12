from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_formatting import format_browser_activity_lines
from shared.web_automation import client as browser_client_module
from shared.web_automation.observe import (
    append_console_entry,
    read_error_entries,
    read_request_entries,
)
from shared.web_automation.service import BrowserService
from shared.web_automation.types import BrowserTab

class BrowserToolDebugRenderingTest(unittest.TestCase):
    def _activity(self, payload: dict, *, ok: bool = True):
        activities = activity_events_for_tool_event(
            ToolEvent(
                name="browser_console",
                ok=ok,
                summary="browser debug",
                payload=payload,
            )
        )
        self.assertEqual(len(activities), 1)
        return activities[0]

    def _assert_line_contains(self, lines: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in line for line in lines), f"missing {fragment!r} in {lines!r}")

    def test_browser_errors_render_as_dedicated_debug_surface(self) -> None:
        activity = self._activity(
            {
                "action": "errors",
                "target_id": "tab-errors",
                "url": "https://example.com/app",
                "entries": [
                    {"level": "error", "message": "Unhandled promise rejection"},
                    {"level": "error", "message": "XHR failed with 500"},
                ],
                "levels": {"error": 2},
                "planner_elapsed_ms": 120,
            }
        )

        self.assertEqual(activity.title, "Browser errors")
        self.assertIn("count=2", activity.detail)
        self.assertIn("level=error", activity.detail)
        lines = format_browser_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser errors")
        self._assert_line_contains(lines, "count=2")
        self._assert_line_contains(lines, "level=error")
        self._assert_line_contains(lines, "msg=Unhandled promise rejection")
        self._assert_line_contains(lines, "levels=error:2")
        self._assert_line_contains(lines, "target=tab-errors")
        self._assert_line_contains(lines, "url=https://example.com/app")
        self._assert_line_contains(lines, "time=0.12s")

    def test_browser_requests_render_method_status_and_outcomes(self) -> None:
        activity = self._activity(
            {
                "action": "requests",
                "target_id": "tab-network",
                "entries": [
                    {
                        "method": "GET",
                        "status": 200,
                        "resource_type": "document",
                        "url": "https://example.com/app",
                        "outcome": "ok",
                    },
                    {
                        "method": "POST",
                        "status": 503,
                        "resource_type": "xhr",
                        "url": "https://example.com/api/login",
                        "outcome": "failed",
                    },
                ],
                "outcomes": {"ok": 1, "failed": 1},
                "planner_elapsed_ms": 50,
            }
        )

        self.assertEqual(activity.title, "Browser requests")
        self.assertIn("count=2", activity.detail)
        self.assertIn("method=GET", activity.detail)
        self.assertIn("status=200", activity.detail)
        lines = format_browser_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser requests")
        self._assert_line_contains(lines, "count=2")
        self._assert_line_contains(lines, "method=GET")
        self._assert_line_contains(lines, "status=200")
        self._assert_line_contains(lines, "resource=document")
        self._assert_line_contains(lines, "url=https://example.com/app")
        self._assert_line_contains(lines, "outcome=ok")
        self._assert_line_contains(lines, "outcomes=failed:1,ok:1")
        self._assert_line_contains(lines, "target=tab-network")
        self._assert_line_contains(lines, "time=0.05s")

    def test_observe_helpers_filter_error_and_request_entries(self) -> None:
        tab = BrowserTab(
            tab_id="tab-1",
            url="https://example.com/app",
            title="App",
            profile="openclaw",
        )
        append_console_entry(tab, message_type="info", text="loaded", location={"url": tab.url})
        append_console_entry(tab, message_type="error", text="render failed", location={"url": tab.url})
        append_console_entry(
            tab,
            message_type="request",
            text="GET /api/profile",
            location={"url": "https://example.com/api/profile", "method": "GET", "status": "200", "outcome": "ok"},
        )
        append_console_entry(
            tab,
            message_type="request",
            text="POST /api/login",
            location={"url": "https://example.com/api/login", "method": "POST", "status": "503", "outcome": "failed"},
        )

        errors = read_error_entries(tab, limit=10)
        requests = read_request_entries(tab, limit=10)
        failed_requests = read_request_entries(tab, limit=10, outcome="failed")
        post_requests = read_request_entries(tab, limit=10, method="POST")

        self.assertEqual([item.text for item in errors], ["render failed"])
        self.assertEqual([item.text for item in requests], ["GET /api/profile", "POST /api/login"])
        self.assertEqual([item.text for item in failed_requests], ["POST /api/login"])
        self.assertEqual([item.text for item in post_requests], ["POST /api/login"])

    def test_runtime_browser_errors_and_requests_commands_use_debug_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/app")
                    tab = browser_client_module._service.list_tabs()[0]
                    append_console_entry(tab, message_type="error", text="render failed", location={"url": tab.url})
                    append_console_entry(
                        tab,
                        message_type="request",
                        text="GET /api/profile",
                        location={
                            "url": "https://example.com/api/profile",
                            "method": "GET",
                            "status": "200",
                            "resource_type": "xhr",
                            "outcome": "ok",
                        },
                    )
                    append_console_entry(
                        tab,
                        message_type="request",
                        text="POST /api/login",
                        location={
                            "url": "https://example.com/api/login",
                            "method": "POST",
                            "status": "503",
                            "resource_type": "xhr",
                            "outcome": "failed",
                        },
                    )

                    errors = runtime.handle_prompt("/browser errors --limit 1").tool_events[0]
                    requests = runtime.handle_prompt("/browser requests --limit 5").tool_events[0]

                    self.assertEqual(errors.name, "browser_console")
                    self.assertTrue(errors.ok)
                    self.assertEqual(errors.payload["action"], "errors")
                    self.assertEqual(errors.payload["count"], 1)
                    self.assertEqual(errors.payload["entries"][0]["message"], "render failed")

                    self.assertEqual(requests.name, "browser_console")
                    self.assertTrue(requests.ok)
                    self.assertEqual(requests.payload["action"], "requests")
                    self.assertEqual(requests.payload["count"], 2)
                    self.assertEqual(requests.payload["entries"][0]["method"], "GET")
                    self.assertEqual(requests.payload["entries"][0]["status"], 200)
                    self.assertEqual(requests.payload["entries"][1]["outcome"], "failed")
                    self.assertEqual(requests.payload["outcomes"], {"ok": 1, "failed": 1})
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)
