from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_root_override_preserves_exact_cli_value(
    monkeypatch,
) -> None:
    root_value = "cli/custom_scope/./nested//../target_scope"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--root",
            root_value,
        ],
    )

    args = import_boundary_guard.parse_args()

    assert args.root == root_value
