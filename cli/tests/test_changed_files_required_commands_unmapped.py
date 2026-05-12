from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_required_commands_unmapped", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_required_commands_returns_empty_for_fully_unmapped_paths() -> None:
    paths = [
        "docs/README.md",
        "scripts/release_helper.py",
        "plugins/demo/sample.yaml",
        "cli/agent_hub/runtime_core/not_guarded.py",
    ]

    assert MODULE.required_commands(paths) == []
