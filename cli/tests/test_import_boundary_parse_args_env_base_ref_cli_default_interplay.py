from __future__ import annotations

import sys
from unittest.mock import patch

from cli.scripts import import_boundary_guard


def test_parse_args_uses_env_base_ref_when_cli_arg_is_absent() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "from-env"}, clear=True):
        with patch.object(sys, "argv", ["import_boundary_guard.py"]):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == "from-env"


def test_parse_args_uses_cli_base_ref_when_explicitly_provided() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "from-env"}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["import_boundary_guard.py", "--base-ref", "from-cli"],
        ):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == "from-cli"
