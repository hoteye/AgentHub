from __future__ import annotations

from pathlib import Path

import yaml


def test_cli_cross_platform_workflow_keeps_manual_dispatch_trigger() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    on_section = dict(payload.get("on") or payload.get(True) or {})
    assert "workflow_dispatch" in on_section
    dispatch = on_section.get("workflow_dispatch")
    assert dispatch in (None, {})
