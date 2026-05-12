from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_defaults_preserve_types_and_values(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(sys, "argv", ["import_boundary_guard.py"])

    args = import_boundary_guard.parse_args()

    assert isinstance(args.root, str)
    assert isinstance(args.base_ref, str)
    assert args.root == "cli/agent_cli"
    assert args.base_ref == ""
