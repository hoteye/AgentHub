from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_main_propagates_failure",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_main_propagates_non_zero_return_code_from_run_commands(capsys) -> None:
    changed = ["cli/agent_cli/runtime_core/command_dispatch.py"]
    selected = ["python -m pytest -q tests/test_runtime_core_modules.py"]

    with patch.object(
        MODULE,
        "parse_args",
        return_value=Namespace(working_dir="cli", base_ref="main"),
    ), patch.object(MODULE, "changed_files", return_value=changed), patch.object(
        MODULE,
        "required_commands",
        return_value=selected,
    ), patch.object(
        MODULE,
        "run_commands",
        return_value=7,
    ) as patched_run:
        rc = MODULE.main()

    out = capsys.readouterr().out
    assert rc == 7
    assert "[test-gate] changed file count: 1" in out
    assert "[test-gate] selected command count: 1" in out
    patched_run.assert_called_once_with(selected, working_dir=Path("cli"))
