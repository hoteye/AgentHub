from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_allows_explicit_root_and_base_ref_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--root",
            "cli/custom_scope",
            "--base-ref",
            "release/2026-04",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert args.root == "cli/custom_scope"
    assert args.base_ref == "release/2026-04"
