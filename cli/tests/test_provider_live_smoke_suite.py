from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "run_provider_live_smoke_suite.py"
SPEC = importlib.util.spec_from_file_location("run_provider_live_smoke_suite", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProviderLiveSmokeSuiteTest(unittest.TestCase):
    def test_build_suite_steps_uses_canonical_default_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_root = Path(temp_dir) / "out"
            args = Namespace(
                repo_root="/repo",
                codex_bin="/bin/codex",
                agenthub_auth="/tmp/agenthub-auth.json",
                codex_auth="/tmp/codex-auth.json",
                base_url="https://relay05.gaccode.com/codex/v1",
                model="gpt-5.4",
                effort="xhigh",
                bridged_runs=1,
                provider_two_turn_timeout=120,
                skip_headless_matrix=False,
                skip_provider_two_turn_continuity=False,
                skip_previous_response_id_rejection=False,
                skip_additional_permissions_exec_contract=False,
                skip_bridged_request_user_input=False,
            )

            steps = MODULE.build_suite_steps(
                args, out_root=out_root, python_executable="/usr/bin/python3"
            )

        self.assertEqual(
            [item.key for item in steps],
            [
                "headless_provider_matrix",
                "provider_two_turn_continuity",
                "previous_response_id_rejection",
                "additional_permissions_exec_contract",
                "bridged_request_user_input",
            ],
        )
        self.assertEqual(steps[0].output_path, str(out_root / "headless_provider_matrix.json"))
        self.assertEqual(steps[1].output_path, str(out_root / "provider_two_turn_live_smoke.json"))
        self.assertEqual(steps[2].output_path, str(out_root / "previous_response_id_rejection"))
        self.assertEqual(
            steps[3].output_path, str(out_root / "additional_permissions_exec_contract")
        )
        self.assertEqual(steps[4].output_path, str(out_root / "request_user_input_bridged"))
        self.assertIn("benchmark_headless_models.py", steps[0].command[1])
        self.assertIn("provider_two_turn_live_smoke.py", steps[1].command[1])
        self.assertIn("openai:gpt_54", steps[1].command)
        self.assertIn("anthropic:claude_sonnet_46", steps[1].command)
        self.assertIn("previous_response_id_rejection_live_harness.py", steps[2].command[1])
        self.assertIn("additional_permissions_exec_live_harness.py", steps[3].command[1])
        self.assertIn("request_user_input_bridged_openai_ab.py", steps[4].command[1])
        self.assertIn("relay05.gaccode.com", " ".join(steps[4].command))

    def test_run_suite_step_skips_when_required_paths_are_missing(self) -> None:
        step = MODULE.SuiteStep(
            key="bridged_request_user_input",
            label="Bridged request_user_input A/B",
            command=("python", "dummy.py"),
            output_path="/tmp/out",
            required_paths=("/tmp/does-not-exist-a", "/tmp/does-not-exist-b"),
        )

        result = MODULE.run_suite_step(step, cwd=Path("/tmp"), dry_run=False)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_required_paths")
        self.assertEqual(
            result["missing_paths"],
            ["/tmp/does-not-exist-a", "/tmp/does-not-exist-b"],
        )

    def test_run_suite_step_reports_passed_command(self) -> None:
        step = MODULE.SuiteStep(
            key="headless_provider_matrix",
            label="Headless provider matrix",
            command=(sys.executable, "-c", "print('ok')"),
            output_path="/tmp/out.json",
        )

        result = MODULE.run_suite_step(step, cwd=ROOT / "cli", dry_run=False)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout_preview"], "ok")
