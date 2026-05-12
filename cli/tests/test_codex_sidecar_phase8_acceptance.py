from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "codex_sidecar_phase8_acceptance.py"
SPEC = importlib.util.spec_from_file_location("codex_sidecar_phase8_acceptance", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CodexSidecarPhase8AcceptanceTest(unittest.TestCase):
    def test_default_acceptance_runs_fake_checks_and_skips_optional_probes(self) -> None:
        results = MODULE.run_fake_acceptance(cwd=ROOT, request_timeout=3)

        self.assertEqual([result.status for result in results], ["pass", "pass", "pass", "pass"])
        self.assertEqual(
            [result.name for result in results],
            [
                "fake_sidecar_turn_lifecycle",
                "fake_sidecar_approval_roundtrip",
                "fake_sidecar_fork_resume",
                "fake_sidecar_crash_reconnect_resume",
            ],
        )

    def test_main_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "phase8.json"
            rc = MODULE.main(
                ["--skip-tui", "--request-timeout", "3", "--output-json", str(report_path)]
            )

            self.assertEqual(rc, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["overall_status"], "pass")
            names = [item["name"] for item in report["results"]]
            self.assertIn("fake_sidecar_turn_lifecycle", names)
            self.assertIn("tui_tab_smoke_probe", names)
            self.assertIn("real_codex_ref_ab_probe", names)

    def test_real_probe_command_omits_fork_without_live_turn(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="initialize: ok\n", stderr="")
        with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.run_real_codex_ref_probe(
                codex_bin=Path("/tmp/codex"),
                cwd=ROOT,
                request_timeout=5,
                turn_timeout=10,
                live_turn=None,
                real_fork=False,
            )

        self.assertEqual(result.status, "pass")
        command = run.call_args.args[0]
        self.assertNotIn("--turn", command)
        self.assertNotIn("--fork", command)

    def test_real_probe_command_includes_live_turn_and_fork(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="turn/completed: ok\n", stderr="")
        with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.run_real_codex_ref_probe(
                codex_bin=Path("/tmp/codex"),
                cwd=ROOT,
                request_timeout=5,
                turn_timeout=10,
                live_turn="只回答 OK",
                real_fork=True,
            )

        self.assertEqual(result.status, "pass")
        command = run.call_args.args[0]
        self.assertIn("--turn", command)
        self.assertIn("只回答 OK", command)
        self.assertIn("--fork", command)

    def test_output_report_marks_fail_when_any_required_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "phase8.json"
            results = [
                MODULE.CheckResult(name="ok", status="pass"),
                MODULE.CheckResult(name="bad", status="fail", error="boom"),
            ]

            MODULE.write_report(report_path, results)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["overall_status"], "fail")
            self.assertEqual(report["results"][1]["error"], "boom")


if __name__ == "__main__":
    unittest.main()
