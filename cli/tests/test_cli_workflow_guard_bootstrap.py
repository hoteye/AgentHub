from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardBootstrapTest(unittest.TestCase):
    def test_modularity_guards_job_bootstrap_precedes_guard_scripts(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        self.assertIn("modularity-guards", jobs)
        job = dict(jobs["modularity-guards"] or {})
        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]

        step_names = [str(step.get("name") or "").strip() for step in steps]

        checkout_idx = step_names.index("Check out repository")
        setup_idx = step_names.index("Set up Python")
        install_idx = step_names.index("Install dependencies")
        size_guard_idx = step_names.index("Enforce file-size guard")
        import_guard_idx = step_names.index("Enforce import boundaries on changed files")
        test_gate_idx = step_names.index("Enforce changed-files test gate")

        self.assertLess(checkout_idx, setup_idx)
        self.assertLess(setup_idx, install_idx)
        self.assertLess(install_idx, size_guard_idx)
        self.assertLess(size_guard_idx, import_guard_idx)
        self.assertLess(import_guard_idx, test_gate_idx)

        size_guard_run = str(steps[size_guard_idx].get("run") or "")
        import_guard_run = str(steps[import_guard_idx].get("run") or "")
        test_gate_run = str(steps[test_gate_idx].get("run") or "")

        self.assertIn("python cli/scripts/quality_size_guard.py", size_guard_run)
        self.assertIn("python cli/scripts/import_boundary_guard.py", import_guard_run)
        self.assertIn("python cli/scripts/changed_files_test_gate.py", test_gate_run)

