from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "additional_permissions_exec_live_harness.py"
SPEC = importlib.util.spec_from_file_location(
    "additional_permissions_exec_live_harness", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AdditionalPermissionsExecLiveHarnessTest(unittest.TestCase):
    def test_agenthub_config_renders_selected_base_url_and_model(self) -> None:
        text = MODULE._agenthub_config("https://relay.example/v1", "gpt-5.4", "high")

        self.assertIn('base_url = "https://relay.example/v1"', text)
        self.assertIn('model = "gpt-5.4"', text)
        self.assertIn('model_reasoning_effort = "high"', text)
        self.assertIn('planner_kind = "openai_responses"', text)

    def test_prompt_and_response_projection_preserve_additional_permissions_shape(self) -> None:
        additional_permissions = {"file_system": {"write": ["/tmp/probe"]}}
        prompt = MODULE._prompt_for_additional_permissions(additional_permissions)

        self.assertIn("with_additional_permissions", prompt)
        self.assertIn('"file_system": {"write": ["/tmp/probe"]}', prompt)

        response = SimpleNamespace(
            assistant_text="",
            commentary_text="planning",
            tool_events=[
                SimpleNamespace(
                    name="shell_approval_requested",
                    ok=True,
                    summary="approval requested",
                    payload={"additional_permissions": additional_permissions},
                )
            ],
            item_events=[{"type": "item.completed"}],
            turn_events=[{"type": "turn.completed"}],
        )
        projected = MODULE._prompt_response_to_dict(response)

        self.assertEqual(projected["commentary_text"], "planning")
        self.assertEqual(projected["tool_events"][0]["name"], "shell_approval_requested")
        self.assertEqual(
            projected["tool_events"][0]["payload"]["additional_permissions"], additional_permissions
        )
