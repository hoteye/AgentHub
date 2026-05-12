from __future__ import annotations

from pathlib import Path

import yaml


def test_cli_cross_platform_modularity_guards_job_display_name_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "modularity-guards" in jobs
    job = dict(jobs["modularity-guards"] or {})
    assert str(job.get("name") or "").strip() == "modularity-guards | ubuntu | py3.13"

    steps = list(job.get("steps") or [])
    step_names = {str(step.get("name") or "").strip() for step in steps if isinstance(step, dict)}
    assert "Run refill-wave focused regressions" in step_names
