from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowMatrixInstallContractTest(unittest.TestCase):
    def test_matrix_jobs_keep_shared_install_dependencies_contract(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
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

            self.assertIn("Install dependencies", step_by_name)
            install_run = str(step_by_name["Install dependencies"].get("run") or "")
            self.assertIn("python -m pip install --upgrade pip", install_run)
            self.assertIn("python -m pip install -r requirements.txt", install_run)
            self.assertIn("python -m pip install -r cli/requirements.txt", install_run)
            self.assertIn("python -m pip install -r requirements-dev.txt", install_run)
