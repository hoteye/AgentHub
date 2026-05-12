from __future__ import annotations

from argparse import Namespace
from unittest.mock import Mock

from cli.scripts import import_boundary_guard


def test_import_boundary_main_no_changes_returns_zero_without_scanning(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root="cli/agent_cli", base_ref="main"),
    )
    monkeypatch.setattr(import_boundary_guard, "changed_python_files", lambda root, base_ref: [])
    scan_mock = Mock(return_value=[])
    monkeypatch.setattr(import_boundary_guard, "scan_file", scan_mock)

    rc = import_boundary_guard.main()
    captured = capsys.readouterr().out

    assert rc == 0
    assert "[import-guard] no changed python files under guard scope" in captured
    scan_mock.assert_not_called()
