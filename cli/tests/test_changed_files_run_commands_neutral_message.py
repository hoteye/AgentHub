from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_run_commands_neutral_message", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_commands_prints_neutral_message_on_exit5_and_continues(capsys) -> None:
    calls: list[list[str]] = []
    return_codes = [5, 0]

    def _fake_run(argv, cwd=None, check=False):
        del check
        calls.append(list(argv))
        assert cwd == Path("cli")
        return SimpleNamespace(returncode=return_codes[len(calls) - 1])

    commands = [
        "python -m pytest -q tests/test_not_collected.py",
        "python -m pytest -q tests/test_runtime_core_modules.py",
    ]
    with patch("subprocess.run", side_effect=_fake_run):
        rc = MODULE.run_commands(commands, working_dir=Path("cli"))

    out = capsys.readouterr().out
    assert rc == 0
    assert len(calls) == 2
    assert "[test-gate] no tests collected for this selector (exit 5); treated as neutral" in out
    assert "[test-gate] run: python -m pytest -q tests/test_runtime_core_modules.py" in out
    assert "[test-gate] failed:" not in out
