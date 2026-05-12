from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_main_working_dir", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_main_passes_working_dir_as_path_to_run_commands() -> None:
    args = Namespace(working_dir="cli/custom_runner", base_ref="main")
    commands = ["python -m pytest -q tests/test_runtime_core_modules.py"]
    with patch.object(MODULE, "parse_args", return_value=args), patch.object(
        MODULE, "changed_files", return_value=["cli/agent_cli/runtime_core/command_dispatch.py"]
    ), patch.object(MODULE, "required_commands", return_value=commands), patch.object(
        MODULE, "run_commands", return_value=0
    ) as run_commands_mock:
        rc = MODULE.main()

    assert rc == 0
    run_commands_mock.assert_called_once_with(commands, working_dir=Path("cli/custom_runner"))
