from __future__ import annotations

from pathlib import Path

import yaml


def test_three_matrix_jobs_keep_checkout_step_on_checkout_v4() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = dict(payload.get("jobs") or {})

    for job_name in ("fast-ui-baseline", "deeper-cli-baseline", "platform-tool-regressions"):
        assert job_name in jobs
        job = dict(jobs[job_name] or {})
        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
        step_by_name = {str(step.get("name") or "").strip(): step for step in steps}

        assert "Check out repository" in step_by_name
        checkout_step = step_by_name["Check out repository"]
        assert str(checkout_step.get("uses") or "").strip() == "actions/checkout@v4"
