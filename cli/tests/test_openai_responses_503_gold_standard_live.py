from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from cli.agent_cli import provider as provider_module
from cli.agent_cli.providers.openai_client import build_openai_client

_OVERRIDE_ENV_NAMES = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "AGENT_CLI_API_KEY",
    "AGENT_CLI_BASE_URL",
    "AGENT_CLI_PROVIDER",
    "AGENT_CLI_MODEL",
    "AGENT_CLI_REASONING_EFFORT",
)

@contextmanager
def _without_provider_override_env():
    previous = {name: os.environ.pop(name) for name in _OVERRIDE_ENV_NAMES if name in os.environ}
    try:
        yield
    finally:
        for name, value in previous.items():
            os.environ[name] = value

@unittest.skipUnless(
    os.environ.get("RUN_LIVE_RESPONSES_503_GOLD_STANDARD") == "1",
    "set RUN_LIVE_RESPONSES_503_GOLD_STANDARD=1 to enable live 503 gold-standard replay",
)
class OpenAIResponses503GoldStandardLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with _without_provider_override_env():
            snapshot = provider_module.load_provider_management_snapshot(cwd=ROOT / "cli")
            cls.config = getattr(snapshot, "selected_config", None)
            if cls.config is None:
                raise unittest.SkipTest("provider config not found")
            if str(cls.config.planner_kind or "").strip().lower() != "openai_responses":
                raise unittest.SkipTest("active provider is not using the Responses planner")
            cls.client = build_openai_client(cls.config)

        base = ROOT / "docs/ab_acceptance/reference_logs/20260331_102338_raw_request_replay"
        cls.recorded_request = json.loads((base / "agenthub.request.json").read_text(encoding="utf-8"))
        cls.reference_request = json.loads((base / "reference.request.json").read_text(encoding="utf-8"))

    def _call(self, payload: dict, *, case_id: str) -> dict:
        request = deepcopy(payload)
        request["store"] = False
        request["stream"] = False
        request["prompt_cache_key"] = f"live-503-gold-{case_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        try:
            response = self.client.responses.create(**request)
            return {
                "ok": True,
                "response_id": str(getattr(response, "id", "") or ""),
                "output_text": str(getattr(response, "output_text", "") or "")[:500],
            }
        except Exception as exc:
            return {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    def test_single_bad_elements_trigger_real_503_while_reference_controls_stay_200(self) -> None:
        results: dict[str, dict] = {}
        results["control_reference_before"] = self._call(self.reference_request, case_id="control-before")
        if not results["control_reference_before"]["ok"]:
            raise unittest.SkipTest(f"baseline reference request failed: {results['control_reference_before']}")

        for index in (3, 5, 6):
            mutated = deepcopy(self.reference_request)
            mutated["input"][index] = deepcopy(self.recorded_request["input"][index])
            key = f"agent_bad_{index}"
            results[key] = self._call(mutated, case_id=key)
            self.assertFalse(results[key]["ok"], key)
            self.assertIn("Error code: 503", results[key]["error"], key)

        results["control_reference_after"] = self._call(self.reference_request, case_id="control-after")
        self.assertTrue(results["control_reference_after"]["ok"], results["control_reference_after"])

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "summary.json"
            artifact.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            self.assertTrue(artifact.exists())
