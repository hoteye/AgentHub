from __future__ import annotations

from pathlib import Path

import yaml


def test_modularity_guards_job_keeps_focused_regression_after_gate_checks() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "modularity-guards" in jobs
    job = dict(jobs["modularity-guards"] or {})
    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
    step_names = [str(step.get("name") or "").strip() for step in steps]

    changed_files_gate_idx = step_names.index("Enforce changed-files test gate")
    focused_regression_idx = step_names.index("Run refill-wave focused regressions")

    assert changed_files_gate_idx < focused_regression_idx
