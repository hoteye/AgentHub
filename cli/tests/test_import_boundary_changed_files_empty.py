from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_changed_python_files_returns_empty_when_diff_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(import_boundary_guard, "diff_base", lambda base_ref: "base_sha")
    monkeypatch.setattr(import_boundary_guard, "run_git", lambda args: "")

    changed = import_boundary_guard.changed_python_files(
        root=Path("cli/agent_cli"),
        base_ref="main",
    )

    assert changed == []


def test_changed_python_files_returns_empty_when_no_path_hits_root(monkeypatch) -> None:
    monkeypatch.setattr(import_boundary_guard, "diff_base", lambda base_ref: "base_sha")
    monkeypatch.setattr(
        import_boundary_guard,
        "run_git",
        lambda args: "\n".join(
            [
                "docs/README.md",
                "scripts/tooling.py",
                "cli/tests/test_import_boundary_guard.py",
                "cli/agent_hub/runtime_core/not_in_root.py",
            ]
        ),
    )

    changed = import_boundary_guard.changed_python_files(
        root=Path("cli/agent_cli"),
        base_ref="main",
    )

    assert changed == []
