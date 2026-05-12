from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.provider import _tool_specs
from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolEvaluateContractTest(unittest.TestCase):
    def test_provider_browser_schema_includes_evaluate_kind_and_fn(self) -> None:
        specs = _tool_specs(current_host_platform())
        browser_spec = next(item for item in specs if item["function"]["name"] == "browser")
        properties = browser_spec["function"]["parameters"]["properties"]
        self.assertIn("evaluate", properties["kind"]["enum"])
        self.assertIn("fn", properties)

class BrowserToolEvaluateExecutionTest(unittest.TestCase):
    def test_runtime_browser_evaluate_is_blocked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/workflow")

                    blocked = runtime.handle_prompt('/browser act evaluate --fn "() => document.title"').tool_events[0]

                    self.assertFalse(blocked.ok)
                    self.assertEqual(blocked.name, "browser_action")
                    self.assertEqual(blocked.payload["action"], "act")
                    self.assertEqual(blocked.payload["kind"], "evaluate")
                    self.assertIn("browser evaluate is disabled", str(blocked.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_evaluate_alias_runs_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(
                    os.environ,
                    {
                        "AGENTHUB_BROWSER_MODE": "synthetic",
                        "AGENTHUB_BROWSER_EVALUATE_ENABLED": "1",
                    },
                    clear=False,
                ):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/workflow")

                    page_eval = runtime.handle_prompt('/browser evaluate --fn "() => document.title"').tool_events[0]
                    ref_eval = runtime.handle_prompt('/browser evaluate --ref r1 --fn "(el) => el.textContent"').tool_events[0]

                    self.assertTrue(page_eval.ok)
                    self.assertEqual(page_eval.payload["action"], "evaluate")
                    self.assertEqual(page_eval.payload["result"]["value"], "https://example.com/workflow")
                    self.assertTrue(ref_eval.ok)
                    self.assertEqual(ref_eval.payload["ref"], "r1")
                    self.assertEqual(ref_eval.payload["result"]["value"], "https://example.com/workflow")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
