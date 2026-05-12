from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_import_boundary_main_outputs_all_failures_for_multi_file_violations(
    monkeypatch, capsys
) -> None:
    file_a = Path("cli/agent_cli/runtime_core/a_violation.py")
    file_b = Path("cli/agent_cli/runtime_services/b_violation.py")

    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root="cli/agent_cli", base_ref="main"),
    )
    monkeypatch.setattr(
        import_boundary_guard,
        "changed_python_files",
        lambda root, base_ref: [file_a, file_b],
    )

    def _scan_file(path: Path) -> list[tuple[int, str]]:
        if path == file_a:
            return [(3, "cli.agent_cli.ui.status")]
        if path == file_b:
            return [(7, "cli.agent_cli.ui.widgets"), (11, "cli.agent_cli.ui")]
        return []

    monkeypatch.setattr(import_boundary_guard, "scan_file", _scan_file)

    rc = import_boundary_guard.main()
    captured = capsys.readouterr().out

    assert rc == 1
    assert "[import-guard] boundary violations:" in captured
    assert (
        "cli/agent_cli/runtime_core/a_violation.py:3 imports forbidden module "
        "'cli.agent_cli.ui.status'"
    ) in captured
    assert (
        "cli/agent_cli/runtime_services/b_violation.py:7 imports forbidden module "
        "'cli.agent_cli.ui.widgets'"
    ) in captured
    assert (
        "cli/agent_cli/runtime_services/b_violation.py:11 imports forbidden module "
        "'cli.agent_cli.ui'"
    ) in captured
