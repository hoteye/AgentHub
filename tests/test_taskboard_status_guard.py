from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_taskboard_status.py"
SPEC = importlib.util.spec_from_file_location("check_taskboard_status", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _status_tokens() -> str:
    return "\n".join(f"- `{status}`" for status in MODULE.ALLOWED_STATUSES)


def _task_card(status: str = "ready", with_do_not_edit: bool = True) -> str:
    lines = [
        "# Task A",
        "",
        "Last updated: 2026-04-11",
        "",
        f"Status: {status}",
        "",
        "Priority: P2",
        "",
        "Owner scope:",
        "",
        "- `a`",
    ]
    if with_do_not_edit:
        lines.extend(["", "Do not edit:", "", "- `b`"])
    return "\n".join(lines) + "\n"


def test_check_repository_passes_for_valid_governance_wave(tmp_path: Path) -> None:
    _write(tmp_path / "taskboard/README.md", f"# Taskboard\n\n{_status_tokens()}\n")
    _write(
        tmp_path / "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md",
        f"# Policy\n\n{_status_tokens()}\n",
    )
    _write(
        tmp_path / "taskboard/repository_governance_wave_02_20260411/README.md",
        "\n".join(
            [
                "# Wave",
                "",
                "Last updated: 2026-04-11",
                "",
                "Wave status: ready",
                "",
                "- [taskbook](../docs/AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md)",
                "",
                "## 当前状态",
                "",
                "- `Task A`：ready",
            ]
        )
        + "\n",
    )
    _write(
        tmp_path
        / "taskboard/repository_governance_wave_02_20260411/TASK_A_owners_coverage_and_drift_guard_p2.md",
        _task_card(status="ready"),
    )

    errors = MODULE.check_repository(tmp_path)
    assert errors == []


def test_check_repository_reports_invalid_status_and_missing_required_field(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "taskboard/README.md", f"# Taskboard\n\n{_status_tokens()}\n")
    _write(
        tmp_path / "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md",
        f"# Policy\n\n{_status_tokens()}\n",
    )
    _write(
        tmp_path / "taskboard/repository_governance_wave_03_20260411/README.md",
        "\n".join(
            [
                "# Wave",
                "",
                "Last updated: 2026-04-11",
                "",
                "Wave status: completed",
                "",
                "- [taskbook](../docs/AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md)",
                "",
                "## 当前状态",
                "",
                "- `Task A`：running",
            ]
        )
        + "\n",
    )
    _write(
        tmp_path
        / "taskboard/repository_governance_wave_03_20260411/TASK_A_demo.md",
        _task_card(status="running", with_do_not_edit=False),
    )

    errors = MODULE.check_repository(tmp_path)

    assert any("unsupported task status 'running'" in message for message in errors)
    assert any("has unsupported status 'running'" in message for message in errors)
    assert any("missing 'Do not edit:'" in message for message in errors)
    assert any("missing CLOSURE_REPORT.md" in message for message in errors)
