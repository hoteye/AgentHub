from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_parse_args_working_dir_override_value",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_working_dir_override_keeps_exact_cli_value() -> None:
    working_dir_value = "./cli/../cli/custom-workdir"

    with patch.dict("os.environ", {}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["changed_files_test_gate.py", "--working-dir", working_dir_value],
        ):
            args = MODULE.parse_args()

    assert args.working_dir == working_dir_value
