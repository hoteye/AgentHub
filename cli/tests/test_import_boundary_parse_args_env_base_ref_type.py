from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_env_base_ref_fallback_keeps_string_type(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "release/2026-04")
    monkeypatch.setattr(sys, "argv", ["import_boundary_guard.py"])

    args = import_boundary_guard.parse_args()

    assert args.base_ref == "release/2026-04"
    assert isinstance(args.base_ref, str)
