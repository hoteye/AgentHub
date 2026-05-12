from __future__ import annotations

import sys
from unittest.mock import patch

from cli.scripts import import_boundary_guard


def test_parse_args_defaults_base_ref_to_empty_without_env_or_cli_override() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with patch.object(sys, "argv", ["import_boundary_guard.py"]):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == ""
