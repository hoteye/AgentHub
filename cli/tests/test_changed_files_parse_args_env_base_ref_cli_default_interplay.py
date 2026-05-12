from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_env_cli_interplay",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_uses_env_when_cli_missing_and_uses_cli_when_present() -> None:
    env_value = "release/2026-04"
    cli_value = "feature/env-cli-priority"

    with patch.dict("os.environ", {"GITHUB_BASE_REF": env_value}, clear=True):
        with patch.object(sys, "argv", ["changed_files_test_gate.py"]):
            args_from_env = MODULE.parse_args()

        with patch.object(
            sys,
            "argv",
            ["changed_files_test_gate.py", "--base-ref", cli_value],
        ):
            args_from_cli = MODULE.parse_args()

    assert args_from_env.base_ref == env_value
    assert args_from_cli.base_ref == cli_value
