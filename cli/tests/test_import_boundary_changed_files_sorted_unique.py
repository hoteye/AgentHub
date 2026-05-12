from __future__ import annotations

from pathlib import Path

from cli.scripts import import_boundary_guard


def test_changed_python_files_returns_unique_sorted_paths_within_root(monkeypatch) -> None:
    monkeypatch.setattr(import_boundary_guard, "diff_base", lambda base_ref: "base_sha")
    monkeypatch.setattr(
        import_boundary_guard,
        "run_git",
        lambda args: "\n".join(
            [
                "cli/agent_cli/runtime_core/zeta.py",
                "docs/README.md",
                "cli/agent_cli/ui/panel.py",
                "cli/agent_cli/runtime_core/zeta.py",
                "cli/agent_cli/runtime_core/alpha.py",
                "cli/agent_cli/runtime_core/alpha.py",
                "cli/agent_hub/runtime_core/not_in_root.py",
                "cli/agent_cli/runtime_core/not_python.txt",
            ]
        ),
    )

    changed = import_boundary_guard.changed_python_files(
        root=Path("cli/agent_cli"),
        base_ref="main",
    )

    assert changed == [
        Path("cli/agent_cli/runtime_core/alpha.py"),
        Path("cli/agent_cli/runtime_core/zeta.py"),
        Path("cli/agent_cli/ui/panel.py"),
    ]
