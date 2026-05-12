from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_import_boundary_main_pass_outputs_summary_and_returns_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root="cli/agent_cli", base_ref="main"),
    )
    monkeypatch.setattr(
        import_boundary_guard,
        "changed_python_files",
        lambda root, base_ref: [Path("cli/agent_cli/runtime_core/safe.py")],
    )
    monkeypatch.setattr(import_boundary_guard, "scan_file", lambda path: [])

    rc = import_boundary_guard.main()
    captured = capsys.readouterr().out

    assert rc == 0
    assert "[import-guard] pass on 1 changed files" in captured


def test_import_boundary_main_fail_outputs_violations_and_returns_one(monkeypatch, capsys) -> None:
    target = Path("cli/agent_cli/runtime_core/violation.py")
    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root="cli/agent_cli", base_ref="main"),
    )
    monkeypatch.setattr(
        import_boundary_guard,
        "changed_python_files",
        lambda root, base_ref: [target],
    )
    monkeypatch.setattr(
        import_boundary_guard,
        "scan_file",
        lambda path: [(3, "cli.agent_cli.ui.status"), (9, "cli.agent_cli.ui.widgets")],
    )

    rc = import_boundary_guard.main()
    captured = capsys.readouterr().out

    assert rc == 1
    assert "[import-guard] boundary violations:" in captured
    assert "cli/agent_cli/runtime_core/violation.py:3 imports forbidden module 'cli.agent_cli.ui.status'" in captured
    assert "cli/agent_cli/runtime_core/violation.py:9 imports forbidden module 'cli.agent_cli.ui.widgets'" in captured
