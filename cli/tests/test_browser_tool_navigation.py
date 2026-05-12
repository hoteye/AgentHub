from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

def _live_browser_available() -> bool:
    return importlib.util.find_spec("playwright") is not None and shutil.which("google-chrome") is not None

class BrowserToolNavigationExecutionTest(unittest.TestCase):
    def test_synthetic_open_navigate_tabs_and_active_tab_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    first = runtime.handle_prompt("/browser open --url https://example.com/a").tool_events[0]
                    second = runtime.handle_prompt("/browser open --url https://example.com/b").tool_events[0]
                    self.assertTrue(first.ok)
                    self.assertTrue(second.ok)
                    first_tab = first.payload["target_id"]
                    second_tab = second.payload["target_id"]

                    tabs_event = runtime.handle_prompt("/browser tabs").tool_events[0]
                    self.assertTrue(tabs_event.ok)
                    self.assertEqual(tabs_event.payload["count"], 2)
                    self.assertEqual(browser_client_module._service.status().active_tab, second_tab)

                    focus_event = runtime.handle_prompt(f"/browser focus {first_tab}").tool_events[0]
                    self.assertTrue(focus_event.ok)
                    self.assertEqual(browser_client_module._service.status().active_tab, first_tab)

                    navigate_event = runtime.handle_prompt("/browser navigate --url https://example.com/docs").tool_events[0]
                    self.assertTrue(navigate_event.ok)
                    self.assertEqual(navigate_event.payload["url"], "https://example.com/docs")
                    self.assertEqual(navigate_event.payload["target_id"], first_tab)

                    tabs_after_nav = runtime.handle_prompt("/browser tabs").tool_events[0]
                    first_tab_payload = next(item for item in tabs_after_nav.payload["tabs"] if item["tab_id"] == first_tab)
                    self.assertEqual(first_tab_payload["url"], "https://example.com/docs")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    @unittest.skipUnless(_live_browser_available(), "playwright + google-chrome required")
    def test_live_navigation_policy_blocks_private_host_before_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(
                    os.environ,
                    {
                        "AGENTHUB_BROWSER_MODE": "live",
                        "AGENTHUB_BROWSER_EXECUTABLE_PATH": shutil.which("google-chrome") or "",
                        "AGENTHUB_BROWSER_HEADLESS": "1",
                    },
                    clear=False,
                ):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()
                    started = runtime.handle_prompt("/browser start").tool_events[0]
                    self.assertTrue(started.ok)

                    opened = runtime.handle_prompt("/browser open --url http://127.0.0.1:8787/").tool_events[0]
                    self.assertFalse(opened.ok)
                    self.assertIn("private network host", str(opened.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
