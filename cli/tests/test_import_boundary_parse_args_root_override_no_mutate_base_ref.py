from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_root_override_keeps_env_backed_base_ref(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "release/2026-04")
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
    assert args.base_ref == "release/2026-04"


def test_import_boundary_parse_args_root_override_does_not_change_cli_base_ref(
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
            "release/hotfix-1",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert args.root == "cli/custom_scope"
    assert args.base_ref == "release/hotfix-1"
