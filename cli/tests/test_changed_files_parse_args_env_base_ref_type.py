from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_parse_args_env_base_ref_type",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_args_env_base_ref_fallback_keeps_string_type() -> None:
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "release/2026-04"}, clear=True):
        with patch.object(sys, "argv", ["changed_files_test_gate.py"]):
            args = MODULE.parse_args()

    assert args.base_ref == "release/2026-04"
    assert isinstance(args.base_ref, str)
