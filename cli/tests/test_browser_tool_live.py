from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

def _live_browser_available() -> bool:
    return (
        importlib.util.find_spec("playwright") is not None
        and shutil.which("google-chrome") is not None
    )

@unittest.skipUnless(_live_browser_available(), "playwright + google-chrome required")
class BrowserToolLiveExecutionTest(unittest.TestCase):
    def test_runtime_browser_live_snapshot_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                fixture = Path(temp_dir) / "live-browser.html"
                fixture.write_text(
                    """<!doctype html>
<html>
  <body>
    <script>
      function triggerDownload(fileName, text) {
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = fileName;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 0);
      }
    </script>
    <h1>Operations Dashboard</h1>
    <p>Open incidents: 3</p>
    <label for="email">Email</label>
    <input id="email" aria-label="Email" placeholder="Email" />
    <label><input id="confirm" type="checkbox" aria-label="Confirm" /> Confirm</label>
    <button id="save" aria-label="Save Button" onclick="console.log('save clicked'); this.textContent='Saved';">Save</button>
    <button id="export" aria-label="Export Report" onclick="triggerDownload('report.csv', 'report-body');">Export</button>
    <button id="delayed-export" aria-label="Delayed Export" onclick="setTimeout(() => triggerDownload('delayed.csv', 'delayed-body'), 300);">Delayed Export</button>
    <button
      id="advance"
      aria-label="Advance"
      onclick="document.body.innerHTML = '<h1>Operations Dashboard</h1><p>Stage 2 ready</p><button id=&quot;advance-2&quot; aria-label=&quot;Advance&quot; onclick=&quot;document.body.setAttribute(\\'data-finished\\',\\'yes\\'); console.log(\\'advance complete\\'); this.textContent=\\'Done\\';&quot;>Advance</button>';"
    >Advance</button>
  </body>
</html>
""",
                    encoding="utf-8",
                )
                fixture_url = fixture.resolve().as_uri()

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

                    started = runtime.handle_prompt("/browser start")
                    self.assertTrue(started.tool_events[0].ok)

                    opened = runtime.handle_prompt(f"/browser open --url {fixture_url}")
                    opened_event = opened.tool_events[0]
                    self.assertTrue(opened_event.ok)
                    tab_id = opened_event.payload["target_id"]

                    snapshot = runtime.handle_prompt("/browser snapshot")
                    snapshot_event = snapshot.tool_events[0]
                    self.assertEqual(snapshot_event.name, "browser_snapshot")
                    self.assertTrue(snapshot_event.ok)
                    self.assertEqual(snapshot_event.payload["target_id"], tab_id)
                    self.assertGreaterEqual(snapshot_event.payload["ref_count"], 4)
                    self.assertIn('Page:', snapshot_event.payload["text"])
                    self.assertIn("Operations Dashboard", snapshot_event.payload["text"])
                    self.assertIn("Open incidents: 3", snapshot_event.payload["text"])
                    self.assertIn('Save Button', snapshot_event.payload["text"])
                    self.assertNotIn("Synthetic browser snapshot", snapshot_event.payload["text"])

                    type_event = runtime.handle_prompt("/browser act type --ref e1 --text alice@example.com").tool_events[0]
                    self.assertTrue(type_event.ok)
                    self.assertEqual(type_event.payload["action"], "type")
                    self.assertEqual(type_event.payload["form_state"]["e1"], "alice@example.com")

                    check_event = runtime.handle_prompt("/browser act check --ref e2").tool_events[0]
                    self.assertTrue(check_event.ok)
                    self.assertEqual(check_event.payload["action"], "check")

                    click_event = runtime.handle_prompt("/browser act click --ref e3").tool_events[0]
                    self.assertTrue(click_event.ok)
                    self.assertEqual(click_event.payload["action"], "click")

                    download_event = runtime.handle_prompt("/browser download --ref e4").tool_events[0]
                    self.assertTrue(download_event.ok)
                    self.assertEqual(download_event.name, "browser_download")
                    self.assertEqual(download_event.payload["ref"], "e4")
                    self.assertEqual(download_event.payload["suggested_filename"], "report.csv")
                    self.assertTrue(Path(download_event.payload["path"]).exists())

                    delayed_click = runtime.handle_prompt("/browser act click --ref e5").tool_events[0]
                    self.assertTrue(delayed_click.ok)
                    wait_download_event = runtime.handle_prompt(
                        "/browser wait_download --time-ms 2000 --path waited/delayed.csv"
                    ).tool_events[0]
                    self.assertTrue(wait_download_event.ok)
                    self.assertEqual(wait_download_event.name, "browser_download")
                    self.assertTrue(str(wait_download_event.payload["path"]).endswith("waited/delayed.csv"))
                    self.assertEqual(wait_download_event.payload["suggested_filename"], "delayed.csv")

                    advance_event = runtime.handle_prompt("/browser act click --ref e6").tool_events[0]
                    self.assertTrue(advance_event.ok)
                    self.assertEqual(advance_event.payload["action"], "click")

                    restored_ref_event = runtime.handle_prompt("/browser act click --ref e6").tool_events[0]
                    self.assertTrue(restored_ref_event.ok)
                    self.assertEqual(restored_ref_event.payload["action"], "click")

                    second_snapshot = runtime.handle_prompt("/browser snapshot").tool_events[0]
                    self.assertIn("Stage 2 ready", second_snapshot.payload["text"])
                    self.assertIn('Done', second_snapshot.payload["text"])

                    console_event = runtime.handle_prompt("/browser console").tool_events[0]
                    self.assertTrue(console_event.ok)
                    messages = [entry["message"] for entry in console_event.payload["entries"]]
                    self.assertIn("save clicked", messages)
                    self.assertIn("advance complete", messages)

                    screenshot_event = runtime.handle_prompt("/browser screenshot").tool_events[0]
                    self.assertTrue(screenshot_event.ok)
                    self.assertEqual(screenshot_event.name, "browser_screenshot")
                    screenshot_path = Path(screenshot_event.payload["path"])
                    self.assertTrue(screenshot_path.exists())
                    self.assertGreater(screenshot_path.stat().st_size, 0)

                    pdf_event = runtime.handle_prompt("/browser pdf").tool_events[0]
                    self.assertTrue(pdf_event.ok)
                    self.assertEqual(pdf_event.name, "browser_pdf")
                    pdf_path = Path(pdf_event.payload["path"])
                    self.assertTrue(pdf_path.exists())
                    self.assertGreater(pdf_path.stat().st_size, 0)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
