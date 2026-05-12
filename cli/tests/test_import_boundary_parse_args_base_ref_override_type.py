from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_explicit_base_ref_preserves_string_type_and_value(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--base-ref",
            "release/2026-04",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert isinstance(args.base_ref, str)
    assert args.base_ref == "release/2026-04"
