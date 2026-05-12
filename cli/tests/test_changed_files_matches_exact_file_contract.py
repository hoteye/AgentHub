from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_matches_exact_file_contract",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matches_exact_file_prefix_contract_without_sibling_false_positive() -> None:
    exact_prefix = "cli/agent_cli/provider.py"

    assert MODULE.matches("cli/agent_cli/provider.py", exact_prefix) is True
    assert MODULE.matches("cli/agent_cli/provider.py/subpath-token", exact_prefix) is True

    assert MODULE.matches("cli/agent_cli/provider_extra.py", exact_prefix) is False
    assert MODULE.matches("cli/agent_cli/providerx.py", exact_prefix) is False
