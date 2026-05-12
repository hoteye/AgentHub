from __future__ import annotations

import io
import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ChangedFilesTestGateTest(unittest.TestCase):
    def test_matches_supports_prefix_and_exact_file(self) -> None:
        self.assertTrue(MODULE.matches("cli/agent_cli/runtime_core/x.py", "cli/agent_cli/runtime_core/"))
        self.assertTrue(MODULE.matches("cli/agent_cli/thread_store_extra.py", "cli/agent_cli/thread_store"))
        self.assertTrue(MODULE.matches("cli/agent_cli/provider.py", "cli/agent_cli/provider.py"))
        self.assertFalse(MODULE.matches("cli/agent_cli/providers_x/demo.py", "cli/agent_cli/providers/"))
        self.assertFalse(MODULE.matches("cli/agent_cli/provider_extra.py", "cli/agent_cli/provider.py"))

    def test_required_commands_deduplicates_when_rules_overlap(self) -> None:
        duplicate = "python -m pytest -q tests/test_runtime_core_modules.py"
        with patch.object(
            MODULE,
            "RULES",
            (
                MODULE.Rule(name="a", prefixes=("a/",), commands=(duplicate,)),
                MODULE.Rule(name="b", prefixes=("b/",), commands=(duplicate, "python -m pytest -q tests/test_ui_slash_controller.py")),
            ),
        ):
            commands = MODULE.required_commands(["a/x.py", "b/y.py"])

        self.assertEqual(
            commands,
            [
                duplicate,
                "python -m pytest -q tests/test_ui_slash_controller.py",
            ],
        )

    def test_main_py_is_mapped_to_runtime_core_rule(self) -> None:
        commands = MODULE.required_commands(["cli/agent_cli/main.py"])
        runtime_rule = next(rule for rule in MODULE.RULES if rule.name == "runtime-core")
        self.assertEqual(commands, list(runtime_rule.commands))

    def test_run_commands_treats_exit_code_5_as_neutral(self) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv, cwd=None, check=False):
            del cwd, check
            calls.append(list(argv))
            if len(calls) == 1:
                return SimpleNamespace(returncode=5)
            return SimpleNamespace(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            rc = MODULE.run_commands(
                [
                    "python -m pytest -q tests/test_not_collected.py",
                    "python -m pytest -q tests/test_runtime_core_modules.py",
                ],
                working_dir=Path("cli"),
            )

        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 2)

    def test_parse_args_accepts_repeated_changed_paths(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "changed_files_test_gate.py",
                "--changed",
                "README.md",
                "--changed",
                "cli/agent_cli/main.py",
            ],
        ):
            args = MODULE.parse_args()

        self.assertEqual(args.changed, ["README.md", "cli/agent_cli/main.py"])
        self.assertEqual(args.working_dir, "cli")
        self.assertEqual(args.base_ref, "")
        self.assertTrue(args.rules_file.endswith("scripts/governance/change_test_gate_rules.yaml"))

    def test_main_prints_matched_rule_explanation(self) -> None:
        with patch.object(
            MODULE,
            "parse_args",
            return_value=Namespace(
                working_dir="cli",
                base_ref="",
                changed=["cli/agent_cli/runtime_core/command_dispatch.py"],
            ),
        ), patch.object(MODULE, "run_commands", return_value=0):
            output = io.StringIO()
            with redirect_stdout(output):
                rc = MODULE.main()

        self.assertEqual(rc, 0)
        captured = output.getvalue()
        self.assertIn("[test-gate] matched rule count: 1", captured)
        self.assertIn("[test-gate] matched rule: runtime-core <-", captured)

    def test_load_rules_reads_json_compatible_yaml_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.yaml"
            rules_path.write_text(
                '{"rules":[{"name":"demo","prefixes":["x/"],"commands":["python -m pytest -q tests/test_x.py"]}]}',
                encoding="utf-8",
            )
            rules = MODULE.load_rules(rules_path)

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].name, "demo")
        self.assertEqual(rules[0].prefixes, ("x/",))
        self.assertEqual(rules[0].commands, ("python -m pytest -q tests/test_x.py",))

    def test_main_returns_2_on_invalid_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "broken.yaml"
            rules_path.write_text("{not-valid-json", encoding="utf-8")
            with patch.object(
                MODULE,
                "parse_args",
                return_value=Namespace(
                    working_dir="cli",
                    base_ref="",
                    changed=["README.md"],
                    rules_file=str(rules_path),
                ),
            ), patch.object(MODULE, "run_commands", return_value=0):
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = MODULE.main()

        self.assertEqual(rc, 2)
        self.assertIn("[test-gate] config error:", output.getvalue())
