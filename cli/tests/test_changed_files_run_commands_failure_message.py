from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_run_commands_failure_message", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_commands_prints_failed_command_message_on_nonzero_non5(capsys) -> None:
    command = "python -m pytest -q tests/test_failure.py"

    def _fake_run(argv, cwd=None, check=False):
        del argv, cwd, check
        return SimpleNamespace(returncode=2)

    with patch("subprocess.run", side_effect=_fake_run):
        rc = MODULE.run_commands([command], working_dir=Path("cli"))

    out = capsys.readouterr().out
    assert rc == 2
    assert f"[test-gate] failed: {command}" in out
