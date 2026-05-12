from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_run_commands_check_false", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_commands_invokes_subprocess_with_check_false() -> None:
    seen_checks: list[bool] = []

    def _fake_run(argv, cwd=None, check=False):
        del argv, cwd
        seen_checks.append(bool(check))
        return SimpleNamespace(returncode=0)

    with patch("subprocess.run", side_effect=_fake_run):
        rc = MODULE.run_commands(
            [
                "python -m pytest -q tests/test_first.py",
                "python -m pytest -q tests/test_second.py",
            ],
            working_dir=Path("cli"),
        )

    assert rc == 0
    assert seen_checks == [False, False]
