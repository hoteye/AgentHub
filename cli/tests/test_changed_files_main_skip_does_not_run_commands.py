from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "changed_files_test_gate_main_skip_does_not_run_commands", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_main_returns_zero_and_never_calls_run_commands_when_no_mapped_commands(
    capsys,
) -> None:
    changed = [
        "docs/readme.md",
        "internal_policy_docs/guide.md",
    ]
    with patch.object(
        MODULE,
        "parse_args",
        return_value=Namespace(working_dir="cli", base_ref="main"),
    ), patch.object(MODULE, "changed_files", return_value=changed), patch.object(
        MODULE,
        "required_commands",
        return_value=[],
    ), patch.object(MODULE, "run_commands", return_value=999) as run_commands_mock:
        rc = MODULE.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "[test-gate] no mapped paths changed; skip"
    run_commands_mock.assert_not_called()
