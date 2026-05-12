from __future__ import annotations

from pathlib import Path

import yaml


def test_modularity_guards_job_has_no_needs_dependency_chain() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "modularity-guards" in jobs
    job = dict(jobs["modularity-guards"] or {})

    # standalone pre-guard: do not depend on upstream needs chain
    assert "needs" not in job
