from __future__ import annotations

from pathlib import Path

import yaml


def test_cli_cross_platform_workflow_top_level_job_catalog_contract() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    expected = [
        "modularity-guards",
        "fast-ui-baseline",
        "deeper-cli-baseline",
        "platform-tool-regressions",
    ]

    assert list(jobs.keys()) == expected
    assert "refill-wave-focused-regressions" not in jobs
