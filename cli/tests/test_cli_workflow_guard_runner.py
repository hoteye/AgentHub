from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardRunnerTest(unittest.TestCase):
    def test_modularity_guards_runner_contract_is_ubuntu_latest(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        self.assertIn("modularity-guards", jobs)
        job = dict(jobs["modularity-guards"] or {})
        self.assertEqual(str(job.get("runs-on") or "").strip(), "ubuntu-latest")
        self.assertEqual(str(job.get("name") or "").strip(), "modularity-guards | ubuntu | py3.13")

        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
        step_by_name = {str(step.get("name") or "").strip(): step for step in steps}
        self.assertIn("Run refill-wave focused regressions", step_by_name)
        self.assertEqual(
            str(step_by_name["Run refill-wave focused regressions"].get("working-directory") or "").strip(),
            "cli",
        )

