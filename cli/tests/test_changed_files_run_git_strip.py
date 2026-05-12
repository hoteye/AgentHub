from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_run_git_strip", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_git_strips_subprocess_stdout() -> None:
    with patch("subprocess.run", return_value=SimpleNamespace(stdout="\n  sha123  \n")):
        out = MODULE.run_git(["rev-parse", "HEAD"])

    assert out == "sha123"
