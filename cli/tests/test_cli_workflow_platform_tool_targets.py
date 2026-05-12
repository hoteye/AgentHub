from __future__ import annotations

from pathlib import Path

import yaml


def test_platform_tool_regressions_job_keeps_key_pytest_targets() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "platform-tool-regressions" in jobs
    job = dict(jobs["platform-tool-regressions"] or {})

    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
    step_by_name = {str(step.get("name") or "").strip(): step for step in steps}
    assert "Run platform tool regressions" in step_by_name

    run_step = step_by_name["Run platform tool regressions"]
    assert str(run_step.get("working-directory") or "").strip() == "cli"

    run_text = str(run_step.get("run") or "")
    run_tokens = run_text.split()
    assert run_tokens[:4] == ["python", "-m", "pytest", "-q"]
    assert run_tokens[4:] == [
        "tests/test_host_platform.py",
        "tests/test_platform_regressions.py",
        "tests/test_provider_status.py",
        "tests/test_provider_tool_specs_shared.py",
        "tests/test_tool_call_payloads.py",
        "tests/replay_integration/test_real_cases.py",
        "tests/replay_integration/test_live_headless_ab.py",
    ]
