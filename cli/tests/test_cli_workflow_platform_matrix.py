from __future__ import annotations

from pathlib import Path

import yaml


def _job(payload: dict, name: str) -> dict:
    jobs = dict(payload.get("jobs") or {})
    assert name in jobs
    return dict(jobs[name] or {})


def test_cli_workflow_platform_matrix_contract_for_three_jobs() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = dict(payload.get("jobs") or {})

    expected_os = ["ubuntu-latest", "macos-latest", "windows-latest"]
    expected_python = ["3.13"]
    expected_matrix_jobs = {
        "fast-ui-baseline",
        "deeper-cli-baseline",
        "platform-tool-regressions",
    }

    for name in expected_matrix_jobs:
        job = _job(payload, name)
        assert str(job.get("runs-on") or "").strip() == "${{ matrix.os }}"

        strategy = dict(job.get("strategy") or {})
        assert strategy.get("fail-fast") is False

        matrix = dict(strategy.get("matrix") or {})
        assert list(matrix.get("os") or []) == expected_os
        assert list(matrix.get("python-version") or []) == expected_python

    actual_matrix_jobs = {
        job_name
        for job_name, job_payload in jobs.items()
        if str(dict(job_payload or {}).get("runs-on") or "").strip() == "${{ matrix.os }}"
    }
    assert actual_matrix_jobs == expected_matrix_jobs

    guard_job = _job(payload, "modularity-guards")
    assert str(guard_job.get("runs-on") or "").strip() == "ubuntu-latest"
    assert "strategy" not in guard_job
