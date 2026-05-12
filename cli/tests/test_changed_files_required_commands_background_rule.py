from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_required_commands_background_rule", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_required_commands_returns_background_rule_commands_for_single_background_path() -> None:
    changed_paths = ["cli/agent_cli/background_tasks/queue_runner.py"]

    commands = MODULE.required_commands(changed_paths)

    background_rule = next(rule for rule in MODULE.RULES if rule.name == "background-tasks")
    assert commands == list(background_rule.commands)
