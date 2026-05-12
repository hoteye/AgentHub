from __future__ import annotations

import unittest
from pathlib import Path

import yaml


def _workflow(name: str) -> dict:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / name
    return dict(yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {})


def _steps(payload: dict, job_name: str) -> dict[str, dict]:
    jobs = dict(payload.get("jobs") or {})
    job = dict(jobs[job_name] or {})
    return {
        str(step.get("name") or "").strip(): dict(step)
        for step in list(job.get("steps") or [])
        if isinstance(step, dict)
    }


class ReleaseWorkflowDependenciesTest(unittest.TestCase):
    def test_cli_release_workflow_installs_dev_test_dependencies_before_ci(self) -> None:
        steps = _steps(_workflow("release-executables.yml"), "build")

        self.assertIn("Install runtime dependencies", steps)
        install_run = str(steps["Install runtime dependencies"].get("run") or "")
        self.assertIn("python -m pip install -r requirements-dev.txt", install_run)

    def test_gui_release_workflow_installs_pytest_dependencies(self) -> None:
        steps = _steps(_workflow("release-gui-desktop.yml"), "build")

        self.assertIn("Install test dependencies", steps)
        install_run = str(steps["Install test dependencies"].get("run") or "")
        self.assertIn("python -m pip install -r requirements-dev.txt", install_run)
