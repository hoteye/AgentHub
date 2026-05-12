from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _commands_for_rule(name: str) -> tuple[str, ...]:
    for rule in MODULE.RULES:
        if rule.name == name:
            return tuple(rule.commands)
    raise AssertionError(f"rule not found: {name}")


def test_default_rules_keep_key_prefix_contracts() -> None:
    runtime_rule = next(rule for rule in MODULE.RULES if rule.name == "runtime-core")
    ui_rule = next(rule for rule in MODULE.RULES if rule.name == "ui")
    providers_rule = next(rule for rule in MODULE.RULES if rule.name == "providers")
    unified_rule = next(rule for rule in MODULE.RULES if rule.name == "unified-tool-layer")

    assert "cli/agent_cli/runtime_core/" in runtime_rule.prefixes
    assert "cli/agent_cli/runtime_services/" in runtime_rule.prefixes
    assert "cli/agent_cli/ui/" in ui_rule.prefixes
    assert "cli/agent_cli/provider.py" in providers_rule.prefixes
    assert "cli/scripts/snapshot_unified_tool_layer.py" in unified_rule.prefixes
    assert "cli/scripts/probe_native_web_search_multi_provider.py" in unified_rule.prefixes
    assert any(
        "tests/test_unified_tool_layer_snapshot_script.py" in command
        for command in unified_rule.commands
    )


def test_required_commands_follow_default_rule_mapping_contract() -> None:
    changed_paths = [
        "cli/agent_cli/runtime_core/command_dispatch.py",
        "cli/agent_cli/ui/status_controller_runtime.py",
        "cli/agent_cli/provider.py",
    ]

    commands = MODULE.required_commands(changed_paths)

    expected_runtime = _commands_for_rule("runtime-core")
    expected_ui = _commands_for_rule("ui")
    expected_providers = _commands_for_rule("providers")

    expected = [
        *expected_runtime,
        *[cmd for cmd in expected_ui if cmd not in expected_runtime],
        *[
            cmd
            for cmd in expected_providers
            if cmd not in expected_runtime and cmd not in expected_ui
        ],
    ]

    assert commands == expected
