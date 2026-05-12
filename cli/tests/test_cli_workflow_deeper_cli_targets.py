from __future__ import annotations

from pathlib import Path

import yaml


def test_deeper_cli_baseline_job_keeps_key_pytest_targets_contract() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    )
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "deeper-cli-baseline" in jobs
    job = dict(jobs["deeper-cli-baseline"] or {})
    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]

    target_step = next(
        step for step in steps if str(step.get("name") or "").strip() == "Run headless baseline"
    )
    assert str(target_step.get("working-directory") or "").strip() == "cli"
    run_text = str(target_step.get("run") or "")
    run_tokens = run_text.split()
    assert run_tokens[:6] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=''",
    ]
    assert run_tokens[6:] == [
        "tests/test_headless_mode.py",
        "tests/test_provider_status.py",
    ]
