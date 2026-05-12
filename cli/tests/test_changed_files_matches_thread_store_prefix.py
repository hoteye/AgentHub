from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_matches_thread_store_prefix", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matches_thread_store_prefix_without_trailing_slash_still_hits_descendants() -> None:
    prefix = "cli/agent_cli/thread_store"
    child_path = "cli/agent_cli/thread_store/snapshots/store.py"

    assert MODULE.matches(child_path, prefix) is True
