from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_matches_directory_negative", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matches_directory_prefix_does_not_hit_similar_sibling_directory_name() -> None:
    prefix = "cli/agent_cli/runtime_core/"
    sibling_path = "cli/agent_cli/runtime_core_extra/dispatcher.py"

    assert MODULE.matches(sibling_path, prefix) is False
