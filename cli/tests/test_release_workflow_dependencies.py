from __future__ import annotations

import subprocess
import tempfile
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

    def test_release_driver_reports_new_commits_when_current_public_tag_exists(self) -> None:
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "release_cli_github.sh"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            publish = root / "publish"
            source.mkdir()
            publish.mkdir()

            (source / "cli" / "agent_cli").mkdir(parents=True)
            (source / "cli" / "scripts").mkdir(parents=True)
            (source / "cli" / "scripts" / "check_release_version.py").write_text(
                (
                    Path(__file__).resolve().parents[2]
                    / "cli"
                    / "scripts"
                    / "check_release_version.py"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (source / "cli" / "agent_cli" / "__init__.py").write_text(
                '__version__ = "1.2.3"\n',
                encoding="utf-8",
            )
            (source / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.2.3] - 2026-05-16\n\n- release\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"], cwd=source, check=True
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "Release AgentHub CLI 1.2.3"],
                cwd=source,
                check=True,
            )
            (source / "README.md").write_text("next change\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Next change"], cwd=source, check=True)

            subprocess.run(["git", "init", "-q"], cwd=publish, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"], cwd=publish, check=True
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=publish, check=True)
            (publish / "README.md").write_text("public\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=publish, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "public"], cwd=publish, check=True)
            subprocess.run(["git", "tag", "cli-v1.2.3"], cwd=publish, check=True)

            result = subprocess.run(
                [
                    "bash",
                    str(script_path),
                    "--source",
                    str(source),
                    "--publish-root",
                    str(publish),
                    "--skip-source-tests",
                    "--skip-public-tests",
                    "--no-watch",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("local public tag already exists: cli-v1.2.3", result.stderr)
            self.assertIn("source HEAD has 1 commit(s) after source release commit", result.stderr)
            self.assertIn(
                "bump cli/agent_cli/__init__.py and CHANGELOG.md to 1.2.4",
                result.stderr,
            )
