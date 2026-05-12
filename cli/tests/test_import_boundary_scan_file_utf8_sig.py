from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_scan_file_handles_utf8_bom_and_detects_forbidden_import(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/runtime_core/utf8_sig_violation.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        b"\xef\xbb\xbfimport cli.agent_cli.ui\n"
        b"from ..runtime_services import helper\n"
    )

    violations = import_boundary_guard.scan_file(target)

    assert violations == [(1, "cli.agent_cli.ui")]
