from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_run_commands_failfast", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_commands_stops_immediately_on_first_nonzero_non5_return_code() -> None:
    calls: list[list[str]] = []

    def _fake_run(argv, cwd=None, check=False):
        del cwd, check
        calls.append(list(argv))
        if len(calls) == 1:
            return SimpleNamespace(returncode=2)
        return SimpleNamespace(returncode=0)

    with patch("subprocess.run", side_effect=_fake_run):
        rc = MODULE.run_commands(
            [
                "python -m pytest -q tests/test_first.py",
                "python -m pytest -q tests/test_second.py",
            ],
            working_dir=Path("cli"),
        )

    assert rc == 2
    assert calls == [["python", "-m", "pytest", "-q", "tests/test_first.py"]]
