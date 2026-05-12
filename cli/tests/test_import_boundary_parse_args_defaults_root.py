from __future__ import annotations

import sys

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_defaults_root_contract(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(sys, "argv", ["import_boundary_guard.py"])

    args = import_boundary_guard.parse_args()

    assert args.root == "cli/agent_cli"
