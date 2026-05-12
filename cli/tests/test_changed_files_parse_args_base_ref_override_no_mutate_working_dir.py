from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_base_ref_override_no_mutate_working_dir", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_base_ref_override_does_not_mutate_default_working_dir() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "main"}, clear=True):
        with patch.object(
            sys,
            "argv",
            ["changed_files_test_gate.py", "--base-ref", "release/2026-04-hotfix"],
        ):
            args = MODULE.parse_args()

    assert isinstance(args.working_dir, str)
    assert args.working_dir == "cli"
