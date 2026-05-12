from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolTabsExecutionTest(unittest.TestCase):
    def test_profiles_tabs_focus_and_close_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    tools = ToolRegistry()
                    runtime = AgentCliRuntime()

                    profiles = tools.browser("profiles")
                    self.assertTrue(profiles.ok)
                    self.assertIn("openclaw", [item["name"] for item in profiles.payload["profiles"]])

                    runtime.handle_prompt("/browser start")
                    first_open = runtime.handle_prompt("/browser open --url https://example.com/a").tool_events[0]
                    second_open = runtime.handle_prompt("/browser open --url https://example.com/b").tool_events[0]
                    first_tab = first_open.payload["target_id"]
                    second_tab = second_open.payload["target_id"]
                    self.assertNotEqual(first_tab, second_tab)

                    tabs_event = runtime.handle_prompt("/browser tabs").tool_events[0]
                    self.assertTrue(tabs_event.ok)
                    self.assertEqual(tabs_event.payload["count"], 2)
                    listed_ids = [item["tab_id"] for item in tabs_event.payload["tabs"]]
                    self.assertEqual(listed_ids, [first_tab, second_tab])

                    focus_event = runtime.handle_prompt(f"/browser focus {first_tab}").tool_events[0]
                    self.assertTrue(focus_event.ok)
                    self.assertEqual(browser_client_module._service.status().active_tab, first_tab)

                    close_event = runtime.handle_prompt(f"/browser close {first_tab}").tool_events[0]
                    self.assertTrue(close_event.ok)
                    self.assertEqual(browser_client_module._service.status().active_tab, second_tab)

                    tabs_after_close = runtime.handle_prompt("/browser tabs").tool_events[0]
                    self.assertEqual(tabs_after_close.payload["count"], 1)
                    self.assertEqual(tabs_after_close.payload["tabs"][0]["tab_id"], second_tab)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
