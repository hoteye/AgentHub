from __future__ import annotations

from pathlib import Path

import yaml


def test_deeper_cli_baseline_job_keeps_display_name_contract() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "deeper-cli-baseline" in jobs
    job = dict(jobs["deeper-cli-baseline"] or {})

    assert str(job.get("name") or "").strip() == "deeper-cli | ${{ matrix.os }} | py${{ matrix.python-version }}"
