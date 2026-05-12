from __future__ import annotations

from pathlib import Path

import yaml


def test_modularity_guards_steps_keep_repo_root_guards_and_cli_focused_regression_contexts() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "cli-cross-platform.yml"
    )
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "modularity-guards" in jobs
    job = dict(jobs["modularity-guards"] or {})
    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
    step_by_name = {str(step.get("name") or "").strip(): step for step in steps}

    for step_name in (
        "Enforce file-size guard",
        "Enforce import boundaries on changed files",
        "Enforce changed-files test gate",
    ):
        assert step_name in step_by_name
        assert "working-directory" not in step_by_name[step_name]

    focused_step_name = "Run refill-wave focused regressions"
    assert focused_step_name in step_by_name
    assert str(step_by_name[focused_step_name].get("working-directory") or "").strip() == "cli"
