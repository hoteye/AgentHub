from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation import config as browser_config_module
from shared.web_automation.service import BrowserService

class BrowserToolStatusExecutionTest(unittest.TestCase):
    def test_stop_cleans_up_tabs_and_active_tab(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    initial = runtime.handle_prompt("/browser status").tool_events[0]
                    self.assertTrue(initial.ok)
                    self.assertFalse(initial.payload["running"])
                    self.assertEqual(initial.payload["tabs"], 0)

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/a")
                    runtime.handle_prompt("/browser open --url https://example.com/b")

                    running = runtime.handle_prompt("/browser status").tool_events[0]
                    self.assertTrue(running.ok)
                    self.assertTrue(running.payload["running"])
                    self.assertEqual(running.payload["tabs"], 2)
                    self.assertIsNotNone(running.payload["active_tab"])

                    stopped = runtime.handle_prompt("/browser stop").tool_events[0]
                    self.assertTrue(stopped.ok)

                    after_stop = runtime.handle_prompt("/browser status").tool_events[0]
                    self.assertTrue(after_stop.ok)
                    self.assertFalse(after_stop.payload["running"])
                    self.assertEqual(after_stop.payload["tabs"], 0)
                    self.assertIsNone(after_stop.payload["active_tab"])

                    tabs_after_stop = runtime.handle_prompt("/browser tabs").tool_events[0]
                    self.assertTrue(tabs_after_stop.ok)
                    self.assertEqual(tabs_after_stop.payload["count"], 0)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_profile_scoped_tabs_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                config_path = Path(temp_dir) / "browser_automation.toml"
                config_path.write_text(
                    "\n".join(
                        [
                            "enabled = true",
                            'mode = "synthetic"',
                            'default_profile = "openclaw"',
                            "",
                            "[profiles.openclaw]",
                            'color = "#FF4500"',
                            'driver = "synthetic"',
                            "",
                            "[profiles.review]",
                            'color = "#228B22"',
                            'driver = "synthetic"',
                        ]
                    ),
                    encoding="utf-8",
                )
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    with patch.object(browser_config_module, "DEFAULT_CONFIG_PATH", config_path):
                        browser_client_module.replace_service(BrowserService())
                        runtime = AgentCliRuntime()

                        runtime.handle_prompt("/browser start")
                        runtime.handle_prompt("/browser start --profile review")

                        default_open = runtime.handle_prompt("/browser open --url https://example.com/default").tool_events[0]
                        review_open = runtime.handle_prompt(
                            "/browser open --profile review --url https://example.com/review"
                        ).tool_events[0]

                        self.assertTrue(default_open.ok)
                        self.assertTrue(review_open.ok)

                        default_tabs = runtime.handle_prompt("/browser tabs").tool_events[0]
                        review_tabs = runtime.handle_prompt("/browser tabs --profile review").tool_events[0]

                        self.assertEqual(default_tabs.payload["count"], 1)
                        self.assertEqual(review_tabs.payload["count"], 1)
                        self.assertEqual(default_tabs.payload["tabs"][0]["profile"], "openclaw")
                        self.assertEqual(review_tabs.payload["tabs"][0]["profile"], "review")
                        self.assertEqual(default_tabs.payload["tabs"][0]["url"], "https://example.com/default")
                        self.assertEqual(review_tabs.payload["tabs"][0]["url"], "https://example.com/review")
                        self.assertNotEqual(
                            default_tabs.payload["tabs"][0]["tab_id"],
                            review_tabs.payload["tabs"][0]["tab_id"],
                        )
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_profiles_command_exposes_profile_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                config_path = Path(temp_dir) / "browser_automation.toml"
                config_path.write_text(
                    "\n".join(
                        [
                            "enabled = true",
                            'mode = "live"',
                            'default_profile = "openclaw"',
                            'executable_path = "/opt/browser/chrome"',
                            "headless = true",
                            "",
                            "[profiles.openclaw]",
                            'color = "#FF4500"',
                            'driver = "live"',
                            'user_data_dir = ".profiles/openclaw"',
                            "",
                            "[profiles.review]",
                            'color = "#228B22"',
                            'driver = "remote-cdp"',
                            'cdp_url = "http://127.0.0.1:9222"',
                            "attach_only = true",
                            "headless = false",
                            'executable_path = "/opt/browser/review-chrome"',
                            'user_data_dir = ".profiles/review"',
                        ]
                    ),
                    encoding="utf-8",
                )
                with patch.object(browser_config_module, "DEFAULT_CONFIG_PATH", config_path):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    profiles = runtime.handle_prompt("/browser profiles").tool_events[0]

                    self.assertTrue(profiles.ok)
                    self.assertEqual(profiles.payload["count"], 3)
                    by_name = {item["name"]: item for item in profiles.payload["profiles"]}

                    self.assertEqual(set(by_name), {"openclaw", "review", "user"})
                    self.assertTrue(by_name["openclaw"]["default"])
                    self.assertEqual(by_name["openclaw"]["driver"], "live")
                    self.assertEqual(by_name["openclaw"]["mode"], "local-managed")
                    self.assertEqual(by_name["openclaw"]["user_data_dir"], ".profiles/openclaw")
                    self.assertTrue(by_name["openclaw"]["capabilities"]["supports_reset"])
                    self.assertTrue(by_name["openclaw"]["capabilities"]["supports_json_tab_endpoints"])
                    self.assertTrue(by_name["openclaw"]["capabilities"]["uses_persistent_playwright"])

                    self.assertFalse(by_name["review"]["default"])
                    self.assertEqual(by_name["review"]["driver"], "remote-cdp")
                    self.assertEqual(by_name["review"]["mode"], "remote-cdp")
                    self.assertTrue(by_name["review"]["is_remote"])
                    self.assertTrue(by_name["review"]["attach_only"])
                    self.assertFalse(by_name["review"]["headless"])
                    self.assertEqual(by_name["review"]["cdp_url"], "http://127.0.0.1:9222")
                    self.assertEqual(by_name["review"]["executable_path"], "/opt/browser/review-chrome")
                    self.assertEqual(by_name["review"]["user_data_dir"], ".profiles/review")
                    self.assertTrue(by_name["review"]["capabilities"]["is_remote"])
                    self.assertTrue(by_name["review"]["capabilities"]["cdp_is_loopback"])
                    self.assertFalse(by_name["review"]["capabilities"]["supports_reset"])

                    self.assertFalse(by_name["user"]["default"])
                    self.assertEqual(by_name["user"]["driver"], "existing-session")
                    self.assertEqual(by_name["user"]["mode"], "local-existing-session")
                    self.assertFalse(by_name["user"]["is_remote"])
                    self.assertTrue(by_name["user"]["attach_only"])
                    self.assertFalse(by_name["user"]["headless"])
                    self.assertTrue(str(by_name["user"]["user_data_dir"]))
                    self.assertTrue(by_name["user"]["capabilities"]["uses_existing_session"])
                    self.assertFalse(by_name["user"]["capabilities"]["uses_chrome_mcp"])
                    self.assertFalse(by_name["user"]["capabilities"]["supports_reset"])
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_status_exposes_cdp_hints_for_remote_and_existing_session_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                config_path = Path(temp_dir) / "browser_automation.toml"
                config_path.write_text(
                    "\n".join(
                        [
                            "enabled = true",
                            'mode = "live"',
                            'default_profile = "openclaw"',
                            "",
                            "[profiles.openclaw]",
                            'color = "#FF4500"',
                            'driver = "live"',
                            "",
                            "[profiles.review]",
                            'color = "#228B22"',
                            'driver = "remote-cdp"',
                            'cdp_url = "http://127.0.0.1:9222"',
                            "attach_only = true",
                        ]
                    ),
                    encoding="utf-8",
                )
                with patch.object(browser_config_module, "DEFAULT_CONFIG_PATH", config_path):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    default_status = runtime.handle_prompt("/browser status").tool_events[0]
                    review_status = runtime.handle_prompt("/browser status --profile review").tool_events[0]
                    user_status = runtime.handle_prompt("/browser status --profile user").tool_events[0]

                    self.assertFalse(default_status.payload["cdp_http"])
                    self.assertFalse(default_status.payload["cdp_ready"])

                    self.assertTrue(review_status.payload["cdp_http"])
                    self.assertFalse(review_status.payload["cdp_ready"])
                    self.assertEqual(review_status.payload["transport"], "cdp")

                    self.assertTrue(user_status.payload["cdp_http"])
                    self.assertFalse(user_status.payload["cdp_ready"])
                    self.assertEqual(user_status.payload["transport"], "existing-session")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
