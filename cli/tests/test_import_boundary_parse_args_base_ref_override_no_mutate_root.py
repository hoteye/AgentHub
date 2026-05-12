from __future__ import annotations

import sys
from unittest.mock import patch

from cli.scripts import import_boundary_guard


def test_parse_args_base_ref_override_keeps_default_root() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "from-env"}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["import_boundary_guard.py", "--base-ref", "from-cli"],
        ):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == "from-cli"
    assert args.root == "cli/agent_cli"


def test_parse_args_base_ref_override_does_not_mutate_explicit_root() -> None:
    root_value = "cli/custom_root_scope"
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "from-env"}, clear=True):
        with patch.object(
            sys,
            "argv",
            [
                "import_boundary_guard.py",
                "--base-ref",
                "from-cli",
                "--root",
                root_value,
            ],
        ):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == "from-cli"
    assert args.root == root_value
