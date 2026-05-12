from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.observe import append_console_entry
from shared.web_automation.service import BrowserService

class BrowserToolArtifactsExecutionTest(unittest.TestCase):
    def test_synthetic_screenshot_and_pdf_emit_expected_payloads_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt("/browser open --url https://example.com/report").tool_events[0]
                    tab_id = opened.payload["target_id"]

                    screenshot = runtime.handle_prompt("/browser screenshot").tool_events[0]
                    pdf = runtime.handle_prompt("/browser pdf").tool_events[0]

                    self.assertEqual(screenshot.name, "browser_screenshot")
                    self.assertEqual(pdf.name, "browser_pdf")
                    self.assertTrue(screenshot.ok)
                    self.assertTrue(pdf.ok)

                    screenshot_path = Path(screenshot.payload["path"])
                    pdf_path = Path(pdf.payload["path"])
                    self.assertTrue(screenshot_path.exists())
                    self.assertTrue(pdf_path.exists())
                    self.assertGreater(int(screenshot.payload["size"]), 0)
                    self.assertGreater(int(pdf.payload["size"]), 0)
                    self.assertEqual(screenshot.payload["format"], "png")
                    self.assertEqual(pdf.payload["format"], "pdf")
                    self.assertEqual(screenshot.payload["target_id"], tab_id)
                    self.assertEqual(pdf.payload["target_id"], tab_id)
                    self.assertEqual(screenshot.payload["url"], "https://example.com/report")
                    self.assertEqual(pdf.payload["url"], "https://example.com/report")
                    self.assertEqual(screenshot.payload["title"], "https://example.com/report")
                    self.assertEqual(pdf.payload["title"], "https://example.com/report")

                    tab = browser_client_module._service.list_tabs()[0]
                    self.assertEqual(len(tab.artifacts), 2)
                    self.assertEqual(tab.artifacts[0].target_id, tab_id)
                    self.assertEqual(tab.artifacts[1].target_id, tab_id)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_console_supports_level_filter_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")
                    tab = browser_client_module._service.list_tabs()[0]
                    append_console_entry(tab, message_type="info", text="loaded dashboard", location={"url": tab.url})
                    append_console_entry(tab, message_type="warn", text="slow response", location={"url": tab.url})
                    append_console_entry(tab, message_type="error", text="export failed", location={"url": tab.url})

                    filtered = runtime.handle_prompt("/browser console --level error --limit 1").tool_events[0]

                    self.assertEqual(filtered.name, "browser_console")
                    self.assertTrue(filtered.ok)
                    self.assertEqual(filtered.payload["count"], 1)
                    self.assertEqual(filtered.payload["level"], "error")
                    self.assertEqual(filtered.payload["message"], "export failed")
                    self.assertEqual(filtered.payload["entries"][0]["message"], "export failed")
                    self.assertEqual(filtered.payload["levels"], {"error": 1})
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_screenshot_supports_element_ref_targeting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")

                    screenshot = runtime.handle_prompt("/browser screenshot --ref r1").tool_events[0]

                    self.assertTrue(screenshot.ok)
                    self.assertEqual(screenshot.payload["ref"], "r1")
                    self.assertEqual(screenshot.payload["format"], "png")
                    tab = browser_client_module._service.list_tabs()[0]
                    self.assertEqual(tab.artifacts[-1].ref, "r1")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_download_creates_specialized_artifact_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt("/browser open --url https://example.com/report").tool_events[0]
                    tab_id = opened.payload["target_id"]

                    download = runtime.handle_prompt("/browser download --ref r1").tool_events[0]

                    self.assertEqual(download.name, "browser_download")
                    self.assertTrue(download.ok)
                    self.assertEqual(download.payload["target_id"], tab_id)
                    self.assertEqual(download.payload["ref"], "r1")
                    self.assertEqual(download.payload["format"], "bin")
                    self.assertTrue(download.payload["suggested_filename"].endswith("r1.bin"))
                    self.assertTrue(Path(download.payload["path"]).exists())
                    tab = browser_client_module._service.list_tabs()[0]
                    self.assertEqual(tab.artifacts[-1].kind, "download")
                    self.assertEqual(tab.artifacts[-1].ref, "r1")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_download_requires_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")

                    download = runtime.handle_prompt("/browser download").tool_events[0]

                    self.assertEqual(download.name, "browser_download")
                    self.assertFalse(download.ok)
                    self.assertIn("download requires ref", str(download.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_download_accepts_safe_relative_output_path_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")

                    safe_download = runtime.handle_prompt("/browser download --ref r1 --path safe/export.csv").tool_events[0]
                    self.assertTrue(safe_download.ok)
                    self.assertTrue(str(safe_download.payload["path"]).endswith("safe/export.csv"))

                    rejected = runtime.handle_prompt("/browser download --ref r1 --path ../escape.csv").tool_events[0]
                    self.assertFalse(rejected.ok)
                    self.assertIn("escaped runtime directory", str(rejected.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_wait_download_supports_synthetic_path_control(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt("/browser open --url https://example.com/report").tool_events[0]

                    waited = runtime.handle_prompt("/browser wait_download --path inbox/delayed.csv").tool_events[0]

                    self.assertEqual(waited.name, "browser_download")
                    self.assertTrue(waited.ok)
                    self.assertEqual(waited.payload["target_id"], opened.payload["target_id"])
                    self.assertTrue(str(waited.payload["path"]).endswith("inbox/delayed.csv"))
                    self.assertEqual(waited.payload["format"], "csv")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_wait_download_rejects_absolute_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")

                    waited = runtime.handle_prompt("/browser wait_download --path /tmp/export.csv").tool_events[0]

                    self.assertEqual(waited.name, "browser_download")
                    self.assertFalse(waited.ok)
                    self.assertIn("relative to runtime directory", str(waited.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_console_rejects_invalid_limit_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    invalid_text = runtime.handle_prompt("/browser console --limit nope")
                    non_positive = runtime.handle_prompt("/browser console --limit -1")

                    self.assertEqual(invalid_text.tool_events, [])
                    self.assertIn(
                        "Usage: /browser console [level <info|warn|warning|error|debug>] [limit <n>]",
                        invalid_text.assistant_text,
                    )
                    self.assertEqual(non_positive.tool_events, [])
                    self.assertIn(
                        "Usage: /browser console [level <info|warn|warning|error|debug>] [limit <n>]",
                        non_positive.assistant_text,
                    )
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    @unittest.skipIf(os.name == "nt", "symlink escape test requires POSIX-style symlink support")
    def test_download_and_wait_download_reject_symlink_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                downloads_root = Path(".web_automation_state/artifacts/downloads")
                downloads_root.mkdir(parents=True, exist_ok=True)
                outside = Path(temp_dir) / "outside"
                outside.mkdir()
                symlink_dir = downloads_root / "link-out"
                symlink_dir.symlink_to(outside, target_is_directory=True)

                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")

                    download = runtime.handle_prompt("/browser download --ref r1 --path link-out/escape.csv").tool_events[0]
                    self.assertFalse(download.ok)
                    self.assertIn("escaped runtime directory", str(download.payload.get("error") or ""))

                    waited = runtime.handle_prompt("/browser wait_download --path link-out/escape.csv").tool_events[0]
                    self.assertFalse(waited.ok)
                    self.assertIn("escaped runtime directory", str(waited.payload.get("error") or ""))
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
