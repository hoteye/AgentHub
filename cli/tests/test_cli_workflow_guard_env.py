from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardEnvTest(unittest.TestCase):
    def test_cli_cross_platform_workflow_has_python_encoding_env_for_guards(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        env = dict(payload.get("env") or {})
        self.assertEqual(str(env.get("PYTHONUTF8") or "").strip(), "1")
        self.assertEqual(str(env.get("PYTHONIOENCODING") or "").strip(), "utf-8")

