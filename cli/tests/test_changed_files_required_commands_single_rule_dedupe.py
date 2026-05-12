from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_required_commands_single_rule_dedupe", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_required_commands_does_not_duplicate_commands_when_one_rule_is_hit_multiple_times() -> None:
    changed_paths = [
        "cli/agent_cli/runtime_core/command_dispatch.py",
        "cli/agent_cli/runtime_services/session_state.py",
    ]

    commands = MODULE.required_commands(changed_paths)

    runtime_rule = next(rule for rule in MODULE.RULES if rule.name == "runtime-core")
    assert commands == list(runtime_rule.commands)
