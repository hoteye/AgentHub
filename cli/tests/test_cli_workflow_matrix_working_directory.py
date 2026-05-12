from __future__ import annotations

from pathlib import Path

import yaml


def test_matrix_jobs_keep_pytest_steps_in_cli_working_directory() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = dict(payload.get("jobs") or {})

    for job_name in ("fast-ui-baseline", "deeper-cli-baseline", "platform-tool-regressions"):
        assert job_name in jobs
        job = dict(jobs[job_name] or {})
        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]

        pytest_steps = [step for step in steps if "pytest" in str(step.get("run") or "")]
        assert pytest_steps, f"{job_name} should contain at least one pytest step"

        for step in pytest_steps:
            assert str(step.get("working-directory") or "").strip() == "cli"
