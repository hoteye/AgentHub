from __future__ import annotations

from pathlib import Path

import yaml


def test_cli_cross_platform_platform_tool_regressions_job_display_name_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "platform-tool-regressions" in jobs
    job = dict(jobs["platform-tool-regressions"] or {})
    assert (
        str(job.get("name") or "").strip()
        == "platform-regressions | ${{ matrix.os }} | py${{ matrix.python-version }}"
    )
