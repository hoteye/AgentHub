from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_import_boundary_main_pass_does_not_print_violation_header(monkeypatch, capsys) -> None:
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
    output = capsys.readouterr().out

    assert rc == 0
    assert "[import-guard] pass on 1 changed files" in output
    assert "[import-guard] boundary violations:" not in output
