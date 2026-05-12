from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_changed_python_files_filters_out_python_files_outside_root(monkeypatch) -> None:
    monkeypatch.setattr(import_boundary_guard, "diff_base", lambda base_ref: "base_sha")
    monkeypatch.setattr(
        import_boundary_guard,
        "run_git",
        lambda args: "\n".join(
            [
                "cli/agent_cli/runtime_core/inside_root.py",
                "cli/agent_hub/runtime_core/outside_root.py",
                "scripts/tooling.py",
            ]
        ),
    )

    changed = import_boundary_guard.changed_python_files(
        root=Path("cli/agent_cli"),
        base_ref="main",
    )

    assert changed == [Path("cli/agent_cli/runtime_core/inside_root.py")]
