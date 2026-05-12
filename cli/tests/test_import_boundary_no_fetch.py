from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "import_boundary_guard.py"
SPEC = importlib.util.spec_from_file_location("import_boundary_guard_no_fetch_test", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ImportBoundaryNoFetchTest(unittest.TestCase):
    def test_diff_base_without_base_ref_does_not_fetch(self) -> None:
        observed_subprocess_args: list[list[str]] = []
        observed_run_git_args: list[list[str]] = []

        def _fake_subprocess_run(argv, **kwargs):
            del kwargs
            observed_subprocess_args.append(list(argv))
            raise AssertionError("subprocess.run should not be called when base_ref is empty")

        def _fake_run_git(args):
            observed_run_git_args.append(list(args))
            if args == ["rev-parse", "HEAD~1"]:
                return "abc123"
            raise AssertionError(f"unexpected run_git args: {args}")

        with patch.object(MODULE.subprocess, "run", side_effect=_fake_subprocess_run):
            with patch.object(MODULE, "run_git", side_effect=_fake_run_git):
                resolved = MODULE.diff_base("")

        self.assertEqual(resolved, "abc123")
        self.assertEqual(observed_subprocess_args, [])
        self.assertEqual(observed_run_git_args, [["rev-parse", "HEAD~1"]])

