from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_root_override_keeps_str_and_raw_value(
    monkeypatch,
) -> None:
    root_value = "cli/custom_scope/../scope_v2"
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

    assert isinstance(args.root, str)
    assert args.root == root_value
