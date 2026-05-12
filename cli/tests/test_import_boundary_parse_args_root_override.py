from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_allows_explicit_root_override(monkeypatch) -> None:
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

    assert args.root == "cli/custom_scope"
