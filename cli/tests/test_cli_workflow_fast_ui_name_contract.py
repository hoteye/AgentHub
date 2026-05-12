from __future__ import annotations

from pathlib import Path

import yaml


def test_fast_ui_baseline_job_keeps_display_name_contract() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "cli-cross-platform.yml"
    )
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "fast-ui-baseline" in jobs
    job = dict(jobs["fast-ui-baseline"] or {})
    assert (
        str(job.get("name") or "").strip()
        == "fast-ui | ${{ matrix.os }} | py${{ matrix.python-version }}"
    )
