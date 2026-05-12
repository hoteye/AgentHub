from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_formatting import (
    format_browser_activity_lines,
    format_web_activity_lines,
)
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolPhase2TranscriptTest(unittest.TestCase):
    def _activity(self, name: str, payload: dict, *, ok: bool = True):
        activities = activity_events_for_tool_event(
            ToolEvent(
                name=name,
                ok=ok,
                summary=name,
                payload=payload,
            )
        )
        self.assertEqual(len(activities), 1)
        return activities[0]

    def _assert_line_contains(self, lines: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in line for line in lines), f"missing {fragment!r} in {lines!r}")

    def test_snapshot_event_rendering_groups_phase2_fields(self) -> None:
        activity = self._activity(
            "browser_snapshot",
            {
                "target_id": "tab-login",
                "url": "https://example.com/login",
                "ref": "snap-login",
                "title": "Login",
                "element_count": 14,
                "ref_count": 5,
                "preview": "Sign in form with username and password fields",
                "planner_elapsed_ms": 1250,
            },
        )

        self.assertEqual(activity.title, "Browser snapshot")
        self.assertEqual(activity.kind, "browser")
        self.assertIn("ref=snap-login", activity.detail)
        self.assertIn("elements=14", activity.detail)
        self.assertIn("time=1.25s", activity.detail)

        lines = format_web_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser snapshot")
        self._assert_line_contains(lines, "ref=snap-login")
        self._assert_line_contains(lines, "target=tab-login")
        self._assert_line_contains(lines, "url=https://example.com/login")
        self._assert_line_contains(lines, "title=Login")
        self._assert_line_contains(lines, "elements=14")
        self._assert_line_contains(lines, "refs=5")
        self._assert_line_contains(lines, "preview=Sign in form with username and password fields")
        self._assert_line_contains(lines, "time=1.25s")

    def test_screenshot_event_rendering_includes_artifact_metadata(self) -> None:
        activity = self._activity(
            "browser_screenshot",
            {
                "path": "artifacts/browser/login.png",
                "target_id": "tab-login",
                "url": "https://example.com/login",
                "format": "png",
                "width": 1440,
                "height": 900,
                "size": 20480,
                "planner_elapsed_ms": 80,
            },
        )

        self.assertEqual(activity.title, "Browser screenshot")
        self.assertIn("path=artifacts/browser/login.png", activity.detail)
        self.assertIn("viewport=1440x900", activity.detail)

        lines = format_browser_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser screenshot")
        self._assert_line_contains(lines, "path=artifacts/browser/login.png")
        self._assert_line_contains(lines, "target=tab-login")
        self._assert_line_contains(lines, "url=https://example.com/login")
        self._assert_line_contains(lines, "format=png")
        self._assert_line_contains(lines, "viewport=1440x900")
        self._assert_line_contains(lines, "size=20480")
        self._assert_line_contains(lines, "time=0.08s")

    def test_pdf_failure_rendering_surfaces_error_and_context(self) -> None:
        activity = self._activity(
            "browser_pdf",
            {
                "target_id": "tab-report",
                "url": "https://example.com/report",
                "path": "artifacts/browser/report.pdf",
                "page_count": 3,
                "error": "print failed",
                "planner_elapsed_ms": 250,
            },
            ok=False,
        )

        self.assertEqual(activity.title, "Browser pdf failed")
        self.assertIn("error=print failed", activity.detail)

        lines = format_browser_activity_lines(activity)
        self.assertEqual(lines[0], "✗ Browser pdf failed")
        self._assert_line_contains(lines, "error=print failed")
        self._assert_line_contains(lines, "path=artifacts/browser/report.pdf")
        self._assert_line_contains(lines, "target=tab-report")
        self._assert_line_contains(lines, "url=https://example.com/report")
        self._assert_line_contains(lines, "pages=3")
        self._assert_line_contains(lines, "time=0.25s")

    def test_download_event_rendering_includes_ref_and_filename(self) -> None:
        activity = self._activity(
            "browser_download",
            {
                "path": "artifacts/browser/report.csv",
                "target_id": "tab-report",
                "ref": "e7",
                "url": "https://example.com/files/report.csv",
                "format": "csv",
                "size": 512,
                "suggested_filename": "report.csv",
                "planner_elapsed_ms": 95,
            },
        )

        self.assertEqual(activity.title, "Browser download")
        self.assertIn("ref=e7", activity.detail)
        self.assertIn("file=report.csv", activity.detail)

        lines = format_browser_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser download")
        self._assert_line_contains(lines, "path=artifacts/browser/report.csv")
        self._assert_line_contains(lines, "target=tab-report")
        self._assert_line_contains(lines, "ref=e7")
        self._assert_line_contains(lines, "url=https://example.com/files/report.csv")
        self._assert_line_contains(lines, "format=csv")
        self._assert_line_contains(lines, "size=512")
        self._assert_line_contains(lines, "file=report.csv")
        self._assert_line_contains(lines, "time=0.10s")

    def test_console_event_rendering_uses_entries_and_level_summary(self) -> None:
        activity = self._activity(
            "browser_console",
            {
                "target_id": "tab-console",
                "url": "https://example.com/app",
                "entries": [
                    {"level": "warn", "message": "popup blocked"},
                    {"level": "error", "message": "network idle timeout"},
                ],
                "levels": {"warn": 1, "error": 1},
                "planner_elapsed_ms": 80,
            },
        )

        self.assertEqual(activity.title, "Browser console")
        self.assertIn("count=2", activity.detail)
        self.assertIn("level=warn", activity.detail)
        self.assertIn("levels=error:1,warn:1", activity.detail)

        lines = format_web_activity_lines(activity)
        self.assertEqual(lines[0], "• Browser console")
        self._assert_line_contains(lines, "count=2")
        self._assert_line_contains(lines, "level=warn")
        self._assert_line_contains(lines, "msg=popup blocked")
        self._assert_line_contains(lines, "levels=error:1,warn:1")
        self._assert_line_contains(lines, "target=tab-console")
        self._assert_line_contains(lines, "url=https://example.com/app")
        self._assert_line_contains(lines, "time=0.08s")

class BrowserToolPhase2ExecutionTest(unittest.TestCase):
    def test_runtime_phase2_actions_emit_specialized_events_and_flattened_payloads(self) -> None:
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
                    opened_event = opened.tool_events[0]
                    self.assertEqual(opened_event.name, "browser_action")
                    self.assertTrue(opened_event.ok)
                    opened_tab = opened_event.payload["target_id"]

                    snapshot = runtime.handle_prompt("/browser snapshot")
                    snapshot_event = snapshot.tool_events[0]
                    self.assertEqual(snapshot_event.name, "browser_snapshot")
                    self.assertTrue(snapshot_event.ok)
                    self.assertEqual(snapshot_event.payload["target_id"], opened_tab)
                    self.assertEqual(snapshot_event.payload["url"], "https://example.com")
                    self.assertEqual(snapshot_event.payload["ref_count"], 1)
                    self.assertEqual(snapshot_event.payload["element_count"], 1)
                    self.assertEqual(snapshot_event.payload["ref"], "r1")
                    self.assertIn("Synthetic browser snapshot", snapshot_event.payload["preview"])

                    console = runtime.handle_prompt("/browser console")
                    console_event = console.tool_events[0]
                    self.assertEqual(console_event.name, "browser_console")
                    self.assertTrue(console_event.ok)
                    self.assertEqual(console_event.payload["target_id"], opened_tab)
                    self.assertEqual(console_event.payload["count"], 1)
                    self.assertEqual(console_event.payload["level"], "info")
                    self.assertEqual(console_event.payload["message"], "Opened synthetic tab for https://example.com")
                    self.assertEqual(console_event.payload["entries"][0]["message"], "Opened synthetic tab for https://example.com")

                    screenshot = runtime.handle_prompt("/browser screenshot")
                    screenshot_event = screenshot.tool_events[0]
                    self.assertEqual(screenshot_event.name, "browser_screenshot")
                    self.assertTrue(screenshot_event.ok)
                    self.assertEqual(screenshot_event.payload["target_id"], opened_tab)
                    self.assertEqual(screenshot_event.payload["format"], "png")
                    self.assertTrue(str(screenshot_event.payload["path"]).endswith(".png"))
                    self.assertGreater(int(screenshot_event.payload["size"]), 0)

                    pdf = runtime.handle_prompt("/browser pdf")
                    pdf_event = pdf.tool_events[0]
                    self.assertEqual(pdf_event.name, "browser_pdf")
                    self.assertTrue(pdf_event.ok)
                    self.assertEqual(pdf_event.payload["target_id"], opened_tab)
                    self.assertEqual(pdf_event.payload["format"], "pdf")
                    self.assertTrue(str(pdf_event.payload["path"]).endswith(".pdf"))
                    self.assertGreater(int(pdf_event.payload["size"]), 0)

                    download = runtime.handle_prompt("/browser download --ref r1")
                    download_event = download.tool_events[0]
                    self.assertEqual(download_event.name, "browser_download")
                    self.assertTrue(download_event.ok)
                    self.assertEqual(download_event.payload["target_id"], opened_tab)
                    self.assertEqual(download_event.payload["ref"], "r1")
                    self.assertTrue(str(download_event.payload["path"]).endswith(".bin"))
                    self.assertGreater(int(download_event.payload["size"]), 0)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
