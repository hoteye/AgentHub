from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_cli_defaults", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_defaults_working_dir_and_env_base_ref_fallback() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "main"}, clear=True):
        with patch.object(sys, "argv", ["changed_files_test_gate.py"]):
            args = MODULE.parse_args()

    assert args.working_dir == "cli"
    assert args.base_ref == "main"


def test_parse_args_cli_base_ref_overrides_github_base_ref_env() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "main"}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["changed_files_test_gate.py", "--base-ref", "release/2026-04"],
        ):
            args = MODULE.parse_args()

    assert args.working_dir == "cli"
    assert args.base_ref == "release/2026-04"
