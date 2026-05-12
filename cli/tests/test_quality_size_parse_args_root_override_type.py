from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_parse_args_root_override_keeps_string_type_and_exact_value() -> None:
    argv_backup = list(sys.argv)
    try:
        sys.argv = [
            "quality_size_guard.py",
            "--root",
            "cli/custom_root",
        ]
        args = quality_size_guard.parse_args()
    finally:
        sys.argv = argv_backup

    assert isinstance(args.root, str)
    assert args.root == "cli/custom_root"
