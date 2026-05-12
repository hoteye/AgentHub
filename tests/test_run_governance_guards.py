from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_governance_guards.py"
SPEC = importlib.util.spec_from_file_location("run_governance_guards", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_commands_for_fast_mode_contains_core_guards() -> None:
    commands = MODULE.commands_for_mode("fast", "python")

    assert ("python", "scripts/check_owners_coverage.py") in commands
    assert ("python", "scripts/check_governance_doc_links.py") in commands
    assert ("python", "scripts/check_taskboard_status.py") in commands
    assert ("python", "scripts/check_governance_workflow_coverage.py") in commands


def test_commands_for_ci_mode_includes_pytest_and_gate_smoke() -> None:
    commands = MODULE.commands_for_mode("ci", "python")

    assert any("tests/test_governance_workflow_coverage_guard.py" in command for command in commands)
    assert any(".github/workflows/governance-guards.yml" in command for command in commands)
    assert (
        "python",
        "cli/scripts/provider_config_boundary_guard.py",
        "--root",
        ".",
    ) in commands


def test_run_commands_stops_on_first_failure(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(argv, cwd=None, check=False):
        del cwd, check
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)

    with patch("subprocess.run", side_effect=fake_run):
        rc = MODULE.run_commands(
            (("python", "a.py"), ("python", "b.py")),
            tmp_path,
        )

    assert rc == 1
    assert calls == [("python", "a.py")]
