from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_run_commands_cwd_contract", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_commands_passes_working_dir_to_subprocess_cwd() -> None:
    calls: list[Path | None] = []

    def _fake_run(argv, cwd=None, check=False):
        del argv, check
        calls.append(cwd)
        return SimpleNamespace(returncode=0)

    working_dir = Path("cli/custom_workdir")
    commands = [
        "python -m pytest -q tests/test_runtime_core_modules.py",
        "python -m pytest -q tests/test_turn_engine_alignment.py",
    ]
    with patch("subprocess.run", side_effect=_fake_run):
        rc = MODULE.run_commands(commands, working_dir=working_dir)

    assert rc == 0
    assert calls == [working_dir, working_dir]
