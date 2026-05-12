from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_no_fetch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_diff_base_does_not_fetch_when_base_ref_is_empty() -> None:
    with patch("subprocess.run") as subprocess_run_mock, patch.object(
        MODULE,
        "run_git",
        return_value="sha_head_parent",
    ) as run_git_mock:
        base = MODULE.diff_base("")

    assert base == "sha_head_parent"
    subprocess_run_mock.assert_not_called()
    run_git_mock.assert_called_once_with(["rev-parse", "HEAD~1"])
