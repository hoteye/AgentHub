from __future__ import annotations

import importlib.util
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, rel_path: str):
    script_path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SIZE_GUARD = _load_module("quality_size_guard_entry_test", "cli/scripts/quality_size_guard.py")
IMPORT_GUARD = _load_module("import_boundary_guard_entry_test", "cli/scripts/import_boundary_guard.py")
TEST_GATE = _load_module("changed_files_test_gate_entry_test", "cli/scripts/changed_files_test_gate.py")


class GuardScriptEntrypointsTest(unittest.TestCase):
    def test_quality_size_guard_parse_args_defaults(self) -> None:
        with patch.object(sys, "argv", ["quality_size_guard.py"]):
            args = SIZE_GUARD.parse_args()

        self.assertEqual(args.root, "cli/agent_cli")
        self.assertEqual(args.soft, 350)
        self.assertEqual(args.hard, 500)
        self.assertEqual(args.baseline, "cli/scripts/size_guard_baseline.json")

    def test_quality_size_guard_main_returns_2_when_root_missing(self) -> None:
        with patch.object(
            SIZE_GUARD,
            "parse_args",
            return_value=Namespace(root="__definitely_missing__", soft=350, hard=500, baseline="x.json"),
        ):
            rc = SIZE_GUARD.main()

        self.assertEqual(rc, 2)

    def test_import_boundary_guard_parse_args_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(sys, "argv", ["import_boundary_guard.py"]):
                args = IMPORT_GUARD.parse_args()

        self.assertEqual(args.root, "cli/agent_cli")
        self.assertEqual(args.base_ref, "")

    def test_import_boundary_guard_main_returns_0_on_empty_changed_set(self) -> None:
        with patch.object(
            IMPORT_GUARD,
            "parse_args",
            return_value=Namespace(root="cli/agent_cli", base_ref="main"),
        ):
            with patch.object(IMPORT_GUARD, "changed_python_files", return_value=[]):
                rc = IMPORT_GUARD.main()

        self.assertEqual(rc, 0)

    def test_changed_files_test_gate_parse_args_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(sys, "argv", ["changed_files_test_gate.py"]):
                args = TEST_GATE.parse_args()

        self.assertEqual(args.working_dir, "cli")
        self.assertEqual(args.base_ref, "")

    def test_changed_files_test_gate_main_returns_0_when_no_mapped_changes(self) -> None:
        with patch.object(
            TEST_GATE,
            "parse_args",
            return_value=Namespace(working_dir="cli", base_ref="main"),
        ):
            with patch.object(TEST_GATE, "changed_files", return_value=["docs/README.md"]):
                with patch.object(TEST_GATE, "required_commands", return_value=[]):
                    rc = TEST_GATE.main()

        self.assertEqual(rc, 0)

