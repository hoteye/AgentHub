from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_scan_file_reports_multiple_forbidden_imports_in_one_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/runtime_core/multi_violation.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import cli.agent_cli.ui\n"
        "import cli.agent_cli.ui.widgets\n"
        "from cli.agent_cli.ui.status import render_status\n"
        "from ..ui import panel\n",
        encoding="utf-8",
    )

    violations = import_boundary_guard.scan_file(target)

    assert violations == [
        (1, "cli.agent_cli.ui"),
        (2, "cli.agent_cli.ui.widgets"),
        (3, "cli.agent_cli.ui.status"),
        (4, "cli.agent_cli.ui"),
    ]


def test_scan_file_returns_empty_when_no_forbidden_imports(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/runtime_core/no_violation.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import cli.agent_cli.runtime_services.helpers\n"
        "from cli.agent_cli.providers import registry\n",
        encoding="utf-8",
    )

    violations = import_boundary_guard.scan_file(target)

    assert violations == []
