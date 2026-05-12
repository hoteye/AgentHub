from __future__ import annotations

import sys
from unittest.mock import patch

from cli.scripts import import_boundary_guard


def test_import_boundary_parse_args_uses_env_base_ref_when_cli_not_provided() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "release/2026-04"}, clear=True):
        with patch.object(sys, "argv", ["import_boundary_guard.py"]):
            args = import_boundary_guard.parse_args()

    assert args.base_ref == "release/2026-04"
