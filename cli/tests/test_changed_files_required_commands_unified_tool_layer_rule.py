from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_required_commands_unified_tool_layer_rule",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _commands_for_rules(*names: str) -> list[str]:
    expected: list[str] = []
    wanted = set(names)
    for rule in MODULE.RULES:
        if rule.name not in wanted:
            continue
        for command in rule.commands:
            if command not in expected:
                expected.append(command)
    return expected


@pytest.mark.parametrize(
    "changed_path",
    [
        "cli/scripts/snapshot_unified_tool_layer.py",
        "cli/scripts/probe_native_web_search_multi_provider.py",
    ],
)
def test_required_commands_returns_unified_tool_layer_commands_for_snapshot_and_probe_paths(
    changed_path: str,
) -> None:
    commands = MODULE.required_commands([changed_path])

    unified_rule = next(rule for rule in MODULE.RULES if rule.name == "unified-tool-layer")
    assert commands == list(unified_rule.commands)


@pytest.mark.parametrize(
    "changed_path",
    [
        "cli/agent_cli/providers/tool_specs.py",
        "cli/agent_cli/providers/builtin_provider_tool_specs.py",
        "cli/agent_cli/providers/responses_tool_specs.py",
        "cli/agent_cli/providers/shared/tool_specs.py",
    ],
)
def test_required_commands_for_unified_spec_paths_include_provider_and_unified_commands(
    changed_path: str,
) -> None:
    commands = MODULE.required_commands([changed_path])

    expected = _commands_for_rules("providers", "unified-tool-layer")
    assert commands == expected
