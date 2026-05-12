from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowModularityGuardStepOrderTest(unittest.TestCase):
    def test_modularity_guards_job_keeps_key_step_order_contract(self) -> None:
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
        changed_files_gate_idx = step_names.index("Enforce changed-files test gate")
        focused_regression_idx = step_names.index("Run refill-wave focused regressions")

        self.assertLess(checkout_idx, setup_idx)
        self.assertLess(setup_idx, install_idx)
        self.assertLess(install_idx, size_guard_idx)
        self.assertLess(size_guard_idx, import_guard_idx)
        self.assertLess(import_guard_idx, changed_files_gate_idx)
        self.assertLess(changed_files_gate_idx, focused_regression_idx)

