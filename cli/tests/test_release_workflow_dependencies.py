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

    def test_cli_release_workflow_authenticates_codex_runtime_downloads(self) -> None:
        steps = _steps(_workflow("release-executables.yml"), "build")

        self.assertIn("Prepare Codex sidecar runtime", steps)
        env = dict(steps["Prepare Codex sidecar runtime"].get("env") or {})
        self.assertEqual(env.get("GITHUB_TOKEN"), "${{ github.token }}")

    def test_cli_release_workflow_runs_clean_install_smoke_after_release(self) -> None:
        steps = _steps(_workflow("release-executables.yml"), "publish")

        self.assertIn("Create GitHub Release", steps)
        self.assertIn("Clean install smoke from GitHub Release", steps)
        smoke_step = steps["Clean install smoke from GitHub Release"]
        self.assertIn("scripts/clean_install_smoke_linux.sh", str(smoke_step.get("run") or ""))
        env = dict(smoke_step.get("env") or {})
        self.assertEqual(env.get("AGENTHUB_INSTALL_REPO"), "${{ github.repository }}")
        self.assertEqual(env.get("AGENTHUB_INSTALL_VERSION"), "${{ github.ref_name }}")

    def test_clean_install_smoke_installs_packaged_cli_runtime_dependencies(self) -> None:
        script_path = (
            Path(__file__).resolve().parents[2] / "scripts" / "clean_install_smoke_linux.sh"
        )
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn(
            "apt-get install -y --no-install-recommends ca-certificates curl git tar gzip",
            script_text,
        )

    def test_gui_release_workflow_installs_pytest_dependencies(self) -> None:
        steps = _steps(_workflow("release-gui-desktop.yml"), "build")

        self.assertIn("Install test dependencies", steps)
        install_run = str(steps["Install test dependencies"].get("run") or "")
        self.assertIn("python -m pip install -r requirements-dev.txt", install_run)
