from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_root_override_beats_default(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--root",
            "cli/custom_root",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert args.root == "cli/custom_root"
    assert args.root != "cli/agent_cli"
