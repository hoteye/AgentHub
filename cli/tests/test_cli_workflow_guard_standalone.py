from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardStandaloneTest(unittest.TestCase):
    def test_modularity_guards_job_is_standalone_without_matrix(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        self.assertIn("modularity-guards", jobs)
        job = dict(jobs["modularity-guards"] or {})

        self.assertEqual(str(job.get("runs-on") or "").strip(), "ubuntu-latest")
        strategy = job.get("strategy")
        self.assertFalse(isinstance(strategy, dict) and "matrix" in strategy)

        name = str(job.get("name") or "").strip()
        self.assertIn("modularity-guards", name)
        self.assertNotIn("${{ matrix.", name)

