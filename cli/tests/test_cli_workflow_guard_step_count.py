from __future__ import annotations

from pathlib import Path

import yaml


def test_modularity_guards_job_keeps_guard_enforcement_steps_and_one_focused_regression_step() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "modularity-guards" in jobs
    job = dict(jobs["modularity-guards"] or {})
    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]

    step_names = [str(step.get("name") or "").strip() for step in steps]
    enforcement_names = [name for name in step_names if name.startswith("Enforce ")]
    focused_names = [name for name in step_names if name == "Run refill-wave focused regressions"]

    assert enforcement_names == [
        "Enforce file-size guard",
        "Enforce import boundaries on changed files",
        "Enforce provider config access boundary on changed files",
        "Enforce changed-files test gate",
    ]
    assert len(enforcement_names) == 4
    assert len(focused_names) == 1
