from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_main_base_ref", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_main_passes_base_ref_arg_to_changed_files() -> None:
    args = Namespace(working_dir="cli", base_ref="release/2026-04")
    with patch.object(MODULE, "parse_args", return_value=args), patch.object(
        MODULE, "changed_files", return_value=["docs/readme.md"]
    ) as changed_files_mock, patch.object(
        MODULE, "required_commands", return_value=[]
    ):
        rc = MODULE.main()

    assert rc == 0
    changed_files_mock.assert_called_once_with("release/2026-04")
