from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_history_rule",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_required_commands_returns_history_rule_commands_for_single_history_hit() -> None:
    changed_paths = ["cli/agent_cli/thread_store/replay_index.py"]

    commands = MODULE.required_commands(changed_paths)
    history_rule = next(rule for rule in MODULE.RULES if rule.name == "history-models")

    assert commands == list(history_rule.commands)
