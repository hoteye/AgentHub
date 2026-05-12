from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_root_stays_string_path(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--root",
            "cli/custom_scope",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert isinstance(args.root, str)
    assert args.root == "cli/custom_scope"
