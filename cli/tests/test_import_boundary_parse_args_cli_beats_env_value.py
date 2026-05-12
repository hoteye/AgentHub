from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_cli_base_ref_beats_env_value(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "from-env")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_boundary_guard.py",
            "--base-ref",
            "from-cli",
        ],
    )

    args = import_boundary_guard.parse_args()

    assert args.base_ref == "from-cli"
