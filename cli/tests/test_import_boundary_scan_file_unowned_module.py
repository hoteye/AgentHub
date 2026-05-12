from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_scan_file_ignores_ui_imports_for_module_outside_owned_prefixes(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/sandbox/unowned_module.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import cli.agent_cli.ui\n"
        "from cli.agent_cli.ui.status import render_status\n",
        encoding="utf-8",
    )

    violations = import_boundary_guard.scan_file(target)

    assert violations == []
