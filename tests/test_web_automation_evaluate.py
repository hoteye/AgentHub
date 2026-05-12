from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.actions import perform_tab_action
from shared.web_automation.config import load_config
from shared.web_automation.types import BrowserPageRef, BrowserTab

class BrowserEvaluateConfigTest(unittest.TestCase):
    def test_load_config_reads_evaluate_enabled_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "browser_automation.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "enabled = true",
                        'mode = "synthetic"',
                        "evaluate_enabled = false",
                    ]
                ),
                encoding="utf-8",
            )

            disabled = load_config(config_path)
            with patch.dict(os.environ, {"AGENTHUB_BROWSER_EVALUATE_ENABLED": "1"}, clear=False):
                enabled = load_config(config_path)

        self.assertFalse(disabled.evaluate_enabled)
        self.assertTrue(enabled.evaluate_enabled)

class BrowserEvaluateSyntheticActionTest(unittest.TestCase):
    def _build_tab(self) -> BrowserTab:
        return BrowserTab(
            tab_id="tab-1",
            url="https://example.com/dashboard",
            title="Operations Dashboard",
            profile="openclaw",
            text="Operations Dashboard\nOpen incidents: 3",
            refs=[
                BrowserPageRef(
                    ref="r1",
                    role="button",
                    name="Save Button",
                    url="https://example.com/dashboard/save",
                    selector='[data-agenthub-ref="r1"]',
                )
            ],
        )

    def test_evaluate_is_blocked_by_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "browser evaluate is disabled"):
            perform_tab_action(
                self._build_tab(),
                kind="evaluate",
                text="() => document.title",
                evaluate_enabled=False,
            )

    def test_evaluate_returns_page_and_ref_values_when_enabled(self) -> None:
        tab = self._build_tab()

        page_result = perform_tab_action(
            tab,
            kind="evaluate",
            text="() => document.title",
            evaluate_enabled=True,
        )
        ref_result = perform_tab_action(
            tab,
            kind="evaluate",
            ref="r1",
            text="(el) => el.textContent",
            evaluate_enabled=True,
        )

        self.assertEqual(page_result["action"] if "action" in page_result else page_result["kind"], "evaluate")
        self.assertEqual(page_result["result"]["value"], "Operations Dashboard")
        self.assertEqual(ref_result["ref"], "r1")
        self.assertEqual(ref_result["result"]["value"], "Save Button")
