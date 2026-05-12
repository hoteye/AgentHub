from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_main_selection", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_main_prints_summary_and_passes_working_dir_to_run_commands(capsys) -> None:
    changed = [
        "cli/agent_cli/runtime_core/command_dispatch.py",
        "cli/agent_cli/ui/status_controller_runtime.py",
        "docs/readme.md",
    ]
    selected = [
        "python -m pytest -q tests/test_runtime_core_modules.py",
        "python -m pytest -q tests/test_ui_operator_status.py",
    ]

    with patch.object(
        MODULE,
        "parse_args",
        return_value=Namespace(working_dir="cli/custom_workdir", base_ref="main"),
    ), patch.object(MODULE, "changed_files", return_value=changed), patch.object(
        MODULE,
        "required_commands",
        return_value=selected,
    ), patch.object(MODULE, "run_commands", return_value=0) as patched_run:
        rc = MODULE.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "[test-gate] changed file count: 3" in out
    assert "[test-gate] selected command count: 2" in out
    patched_run.assert_called_once_with(selected, working_dir=Path("cli/custom_workdir"))
