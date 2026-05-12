from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_parse_args_working_dir_override_no_mutate_base_ref",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_working_dir_override_does_not_change_env_fallback_base_ref() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "release/2026-04"}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["changed_files_test_gate.py", "--working-dir", "cli/custom-dir"],
        ):
            args = MODULE.parse_args()

    assert args.working_dir == "cli/custom-dir"
    assert args.base_ref == "release/2026-04"


def test_parse_args_working_dir_override_does_not_change_cli_base_ref_override() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "from-env"}, clear=True):
        with patch.object(
            sys,
            "argv",
            [
                "changed_files_test_gate.py",
                "--working-dir",
                "cli/another-dir",
                "--base-ref",
                "from-cli",
            ],
        ):
            args = MODULE.parse_args()

    assert args.working_dir == "cli/another-dir"
    assert args.base_ref == "from-cli"
