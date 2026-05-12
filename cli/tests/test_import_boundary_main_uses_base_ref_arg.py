from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_import_boundary_main_passes_parse_args_base_ref_to_changed_python_files(
    monkeypatch, capsys
) -> None:
    expected_root = "cli/agent_cli"
    expected_base_ref = "release/2026-04"
    seen_calls: list[tuple[Path, str]] = []

    def _changed_python_files(root: Path, base_ref: str) -> list[Path]:
        seen_calls.append((root, base_ref))
        return []

    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root=expected_root, base_ref=expected_base_ref),
    )
    monkeypatch.setattr(
        import_boundary_guard,
        "changed_python_files",
        _changed_python_files,
    )

    rc = import_boundary_guard.main()
    captured = capsys.readouterr().out

    assert rc == 0
    assert "[import-guard] no changed python files under guard scope" in captured
    assert seen_calls == [(Path(expected_root), expected_base_ref)]
