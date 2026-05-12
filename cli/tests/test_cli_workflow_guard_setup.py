from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardSetupTest(unittest.TestCase):
    def test_modularity_guards_job_keeps_python_and_install_contract(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        )
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        self.assertIn("modularity-guards", jobs)
        job = dict(jobs["modularity-guards"] or {})
        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
        step_by_name = {str(step.get("name") or "").strip(): step for step in steps}

        self.assertIn("Set up Python", step_by_name)
        setup_step = step_by_name["Set up Python"]
        self.assertEqual(str(setup_step.get("uses") or "").strip(), "actions/setup-python@v5")
        setup_with = dict(setup_step.get("with") or {})
        self.assertEqual(str(setup_with.get("python-version") or "").strip(), "3.13")

        self.assertIn("Install dependencies", step_by_name)
        install_step = step_by_name["Install dependencies"]
        install_run = str(install_step.get("run") or "")
        self.assertIn("python -m pip install --upgrade pip", install_run)
        self.assertIn("python -m pip install -r requirements.txt", install_run)
        self.assertIn("python -m pip install -r cli/requirements.txt", install_run)
        self.assertIn("python -m pip install -r requirements-dev.txt", install_run)
