from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowMatrixSetupContractTest(unittest.TestCase):
    def test_matrix_jobs_keep_shared_python_setup_contract(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[2]
            / ".github"
            / "workflows"
            / "cli-cross-platform.yml"
        )
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        target_jobs = (
            "fast-ui-baseline",
            "deeper-cli-baseline",
            "platform-tool-regressions",
        )
        actual_matrix_jobs = {
            job_name
            for job_name, job_payload in jobs.items()
            if str(dict(job_payload or {}).get("runs-on") or "").strip() == "${{ matrix.os }}"
        }
        self.assertEqual(actual_matrix_jobs, set(target_jobs))

        for job_name in target_jobs:
            self.assertIn(job_name, jobs)
            job = dict(jobs[job_name] or {})
            steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
            step_by_name = {str(step.get("name") or "").strip(): step for step in steps}

            self.assertIn("Set up Python", step_by_name)
            setup_step = step_by_name["Set up Python"]
            self.assertEqual(str(setup_step.get("uses") or "").strip(), "actions/setup-python@v5")

            setup_with = dict(setup_step.get("with") or {})
            self.assertEqual(
                str(setup_with.get("python-version") or "").strip(),
                "${{ matrix.python-version }}",
            )

