from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_main_skip", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_changed_files_main_returns_zero_and_prints_skip_when_no_mapped_commands(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "argv", ["changed_files_test_gate.py", "--base-ref", "main"])
    with patch.object(MODULE, "changed_files", return_value=["docs/README.md"]), patch.object(
        MODULE, "run_commands"
    ) as run_commands_mock:
        rc = MODULE.main()

    output = capsys.readouterr().out
    assert rc == 0
    assert output.strip() == "[test-gate] no mapped paths changed; skip"
    run_commands_mock.assert_not_called()
