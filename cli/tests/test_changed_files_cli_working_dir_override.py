from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_working_dir_override",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_cli_working_dir_overrides_default() -> None:
    with patch.object(
        sys,
        "argv",
        ["changed_files_test_gate.py", "--working-dir", "cli/custom"],
    ):
        args = MODULE.parse_args()

    assert args.working_dir == "cli/custom"
    assert args.base_ref == ""
