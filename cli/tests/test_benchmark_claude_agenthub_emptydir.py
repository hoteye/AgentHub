from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cli.tests.provider_boundary_test_support import (
    assert_provider_home_absent,
    assert_provider_home_env,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "benchmark_claude_agenthub_emptydir.py"
SPEC = importlib.util.spec_from_file_location("benchmark_claude_agenthub_emptydir", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BenchmarkClaudeAgentHubEmptyDirTest(unittest.TestCase):
    def test_default_tasks_define_three_unique_ids(self) -> None:
        tasks = MODULE._default_tasks()
        self.assertEqual(
            [task.task_id for task in tasks], ["ranges_cli", "expense_report", "notes_server"]
        )

    def test_resolve_tasks_filters_subset_and_deduplicates(self) -> None:
        tasks = MODULE._resolve_tasks(["notes_server", "ranges_cli", "notes_server"])
        self.assertEqual([task.task_id for task in tasks], ["notes_server", "ranges_cli"])

    def test_build_claude_command_uses_json_sonnet_and_bypass_permissions(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args([])
        command = MODULE._build_claude_command(prompt="do work", args=args)
        self.assertEqual(
            command[:7],
            ["claude", "-p", "--output-format", "json", "--model", "sonnet", "--permission-mode"],
        )
        self.assertIn("bypassPermissions", command)
        self.assertEqual(command[-1], "do work")

    def test_build_agenthub_command_sets_headless_and_safe_runtime_flags(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.agenthub_provider, "anthropic")
        self.assertEqual(args.agenthub_model, "claude-sonnet-4-6")
        command = MODULE._build_agenthub_command(prompt="do work", args=args)
        self.assertEqual(command[0], sys.executable)
        self.assertIn("--headless", command)
        self.assertIn("--json", command)
        self.assertIn("--approval-policy", command)
        self.assertIn("never", command)
        self.assertIn("--sandbox-mode", command)
        self.assertIn("danger-full-access", command)
        self.assertEqual(command[-2:], ["--prompt", "do work"])

    def test_build_agenthub_env_omits_provider_home_when_unset(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args([])
        env = MODULE._build_agenthub_env(args)

        self.assertEqual(env["AGENT_CLI_PROVIDER"], "anthropic")
        self.assertEqual(env["AGENT_CLI_MODEL"], "claude-sonnet-4-6")
        assert_provider_home_absent(env)

    def test_build_agenthub_env_enables_strict_isolation_when_provider_home_explicit(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args(["--agenthub-provider-home", "/tmp/provider-home"])
        env = MODULE._build_agenthub_env(args)

        assert_provider_home_env(env, "/tmp/provider-home")

    def test_parse_claude_output_reads_result_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stdout.json"
            path.write_text(
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "result": "done",
                        "duration_ms": 1234,
                        "duration_api_ms": 900,
                        "session_id": "abc",
                        "total_cost_usd": 0.12,
                        "usage": {"input_tokens": 10},
                        "modelUsage": {"output_tokens": 20},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            parsed = MODULE._parse_claude_output(path)
            self.assertEqual(parsed["assistant_text"], "done")
            self.assertEqual(parsed["duration_ms"], 1234)
            self.assertEqual(parsed["duration_api_ms"], 900)
            self.assertEqual(parsed["session_id"], "abc")
            self.assertEqual(parsed["usage"]["input_tokens"], 10)
            self.assertEqual(parsed["model_usage"]["output_tokens"], 20)
            self.assertIn("diagnostics", parsed)
            self.assertIsNone(parsed["time_to_first_event_ms"])

    def test_parse_agenthub_output_reads_assistant_text_and_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stdout.json"
            path.write_text(
                json.dumps(
                    {
                        "assistant_text": "built it",
                        "tool_events": [
                            {
                                "name": "apply_patch",
                                "t_rel_ms": 1500,
                                "ok": False,
                                "error": "invalid add-file line",
                            },
                            {
                                "name": "exec_command",
                                "t_rel_ms": 1800,
                                "command": "cat > src/range_tools.py",
                            },
                        ],
                        "turn_events": [{"kind": "message", "t_rel_ms": 1000}],
                        "status": {
                            "thread_id": "thread-1",
                            "timing_initial_model_ms": 1200,
                            "timing_tool_execution_ms": 345,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            parsed = MODULE._parse_agenthub_output(path)
            self.assertEqual(parsed["assistant_text"], "built it")
            self.assertEqual(parsed["thread_id"], "thread-1")
            self.assertEqual(parsed["tool_event_count"], 2)
            self.assertEqual(parsed["turn_event_count"], 1)
            self.assertEqual(parsed["time_to_first_event_ms"], 1000)
            self.assertEqual(parsed["time_to_first_tool_ms"], 1500)
            self.assertEqual(parsed["initial_model_ms"], 1200)
            self.assertEqual(parsed["tool_execution_ms"], 345)
            self.assertEqual(parsed["apply_patch_attempts"], 1)
            self.assertEqual(parsed["apply_patch_failures"], 1)
            self.assertEqual(parsed["fallback_edit_path_count"], 1)
            self.assertEqual(parsed["tool_call_sequence"], ["apply_patch", "exec_command"])

    def test_parse_agenthub_output_has_stable_empty_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing.json"
            parsed = MODULE._parse_agenthub_output(path)
            for key in MODULE._DIAGNOSTIC_FIELD_DEFAULTS:
                self.assertIn(key, parsed)
            self.assertEqual(parsed["tool_call_sequence"], [])
            self.assertEqual(parsed["created_files"], [])
            self.assertFalse(parsed["validation_passed"])

    def test_short_reply_ok_normalizes_trailing_punctuation(self) -> None:
        self.assertTrue(MODULE._short_reply_ok("OK"))
        self.assertTrue(MODULE._short_reply_ok("OK."))
        self.assertTrue(MODULE._short_reply_ok(" ok。 "))
        self.assertFalse(MODULE._short_reply_ok("好的"))

    def test_preflight_checks_validate_expected_routes(self) -> None:
        claude_checks = MODULE._claude_preflight_checks(
            {
                "assistant_text": "OK.",
                "result_subtype": "success",
                "model_usage": {"claude-sonnet-4-6": {"outputTokens": 1}},
            }
        )
        agenthub_checks = MODULE._agenthub_preflight_checks(
            {
                "assistant_text": "OK",
                "status": {
                    "provider_name": "anthropic",
                    "model_key": "claude-sonnet-4-6",
                },
            }
        )
        self.assertTrue(MODULE._checks_passed(claude_checks))
        self.assertTrue(MODULE._checks_passed(agenthub_checks))

    def test_validation_passed_accepts_zero_exit_codes(self) -> None:
        self.assertTrue(
            MODULE._validation_passed(
                [
                    {"exit_code": 0, "timed_out": False},
                    {"exit_code": 0, "timed_out": False},
                ]
            )
        )
        self.assertFalse(MODULE._validation_passed([{"exit_code": 1, "timed_out": False}]))
        self.assertFalse(MODULE._validation_passed([{"exit_code": 0, "timed_out": True}]))

    def test_run_command_writes_timeline_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logger = MODULE.TimelineLogger(root / "timeline.jsonl")
            result = MODULE._run_command(
                name="echo",
                command=["/bin/bash", "-lc", "printf hi"],
                cwd=root,
                env=dict(os.environ),
                stdout_path=root / "stdout.log",
                stderr_path=root / "stderr.log",
                timeout_seconds=10,
                logger=logger,
                event_context={"task_id": "demo", "system": "agenthub"},
            )
            self.assertEqual(result.exit_code, 0)
            events = [
                json.loads(line)
                for line in (root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in events], ["command.started", "command.completed"]
            )
            self.assertEqual(events[0]["task_id"], "demo")
            self.assertEqual(events[1]["system"], "agenthub")

    def test_run_validation_writes_validation_completion_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logger = MODULE.TimelineLogger(root / "timeline.jsonl")
            result = MODULE._run_validation(
                validation=MODULE.ValidationSpec(name="check", command="printf ok"),
                cwd=root,
                env=dict(os.environ),
                out_dir=root / "validation",
                timeout_seconds=10,
                logger=logger,
                event_context={"task_id": "demo", "system": "agenthub"},
            )
            self.assertEqual(result.exit_code, 0)
            events = [
                json.loads(line)
                for line in (root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            event_names = [event["event"] for event in events]
            self.assertEqual(
                event_names,
                [
                    "validation.started",
                    "command.started",
                    "command.completed",
                    "validation.completed",
                ],
            )
            self.assertEqual(events[-1]["validation_name"], "check")
            self.assertEqual(events[-1]["system"], "agenthub")

    def test_run_task_executes_agenthub_and_claude_concurrently(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args([])
        task = MODULE._default_tasks()[0]
        starts: dict[str, float] = {}
        lock = threading.Lock()

        def fake_execute_system(*, system_name: str, **_: object) -> dict[str, object]:
            with lock:
                starts[system_name] = time.perf_counter()
            time.sleep(0.2)
            return {
                "system": system_name,
                "assistant_text": f"{system_name} ok",
                "assistant_preview": f"{system_name} ok",
                "workspace_file_count": 0,
                "workspace_files": [],
                "missing_expected_files": [],
                "validation": [],
                "validation_passed": True,
                "run_succeeded": True,
                "workspace_tree_path": "",
                "run": {"elapsed_seconds": 0.2, "exit_code": 0, "timed_out": False},
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(MODULE, "_execute_system", side_effect=fake_execute_system):
                result = MODULE._run_task(task, root=Path(tmpdir), args=args)
        self.assertEqual(result["agenthub"]["assistant_text"], "agenthub ok")
        self.assertEqual(result["claude"]["assistant_text"], "claude ok")
        self.assertIn("agenthub", starts)
        self.assertIn("claude", starts)
        self.assertLess(abs(starts["agenthub"] - starts["claude"]), 0.15)

    def test_main_dry_run_writes_report_for_selected_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = MODULE.main(
                    [
                        "--dry-run",
                        "--json",
                        "--task",
                        "ranges_cli",
                        "--out-dir",
                        tmpdir,
                    ]
                )
            self.assertEqual(exit_code, 0)
            report = json.loads(stdout.getvalue())
            self.assertTrue(report["dry_run"])
            self.assertEqual(len(report["tasks"]), 1)
            self.assertEqual(report["tasks"][0]["task_id"], "ranges_cli")
            self.assertFalse(report["preflight"]["executed"])
            self.assertTrue((Path(tmpdir) / "timeline.jsonl").exists())
            self.assertEqual(report["timeline_path"], str(Path(tmpdir) / "timeline.jsonl"))
            self.assertEqual(
                report["tasks"][0]["agenthub"]["planned_run_command"][0], sys.executable
            )
            self.assertEqual(report["tasks"][0]["claude"]["planned_run_command"][0], "claude")
            self.assertIn("run", report["tasks"][0]["agenthub"])
            self.assertIn("validation", report["tasks"][0]["agenthub"])
            self.assertIn("parsed_output", report["tasks"][0]["agenthub"])
            self.assertIn("diagnostics", report["tasks"][0]["agenthub"]["parsed_output"])
            self.assertEqual(report["task_workers"], 1)
            self.assertEqual(report["system_execution_mode"], "parallel")
            self.assertEqual(report["scoreboard"][0]["run_successes"], 0)
            self.assertEqual(report["schema_version"], "anthropic_coding_benchmark_v1")
            self.assertEqual(report["agenthub_provider_home_override"], "")
            self.assertEqual(report["agenthub_provider_home_source"], "runtime_default")
            for system_name in ("agenthub", "claude"):
                system = report["tasks"][0][system_name]
                for key in MODULE._DIAGNOSTIC_FIELD_DEFAULTS:
                    self.assertIn(key, system)
                self.assertIn("diagnostics", system)
                self.assertIsNone(system["time_to_first_event_ms"])
                self.assertIsNone(system["time_to_first_tool_ms"])
                self.assertEqual(system["tool_call_sequence"], [])
                self.assertEqual(system["created_files"], [])
                self.assertFalse(system["validation_passed"])
                self.assertIn("dry_run", system["artifact_quality_notes"])
            self.assertTrue((Path(tmpdir) / "report.json").exists())
            summary = Path(tmpdir) / "summary.md"
            self.assertTrue(summary.exists())
            summary_text = summary.read_text(encoding="utf-8")
            self.assertIn("## Diagnostics", summary_text)
            self.assertIn("Tool Sequence", summary_text)
            self.assertIn("Artifact Notes", summary_text)

    def test_main_rejects_unknown_task(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.main(["--task", "does_not_exist"])

    def test_main_rejects_non_positive_task_workers(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.main(["--task-workers", "0"])

    def test_main_aborts_when_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_preflight = {
                "executed": True,
                "passed": False,
                "prompt": MODULE.DEFAULT_PREFLIGHT_PROMPT,
                "systems": {
                    "claude": {
                        "passed": False,
                        "assistant_text": "",
                        "parsed_output": {},
                        "run": {"exit_code": 1},
                    },
                    "agenthub": {
                        "passed": True,
                        "assistant_text": "OK",
                        "parsed_output": {},
                        "run": {"exit_code": 0},
                    },
                },
            }
            with mock.patch.object(MODULE, "_run_preflight", return_value=fake_preflight):
                with mock.patch.object(MODULE, "_run_task") as run_task:
                    exit_code = MODULE.main(["--out-dir", tmpdir])
            self.assertEqual(exit_code, 2)
            run_task.assert_not_called()
            payload = json.loads((Path(tmpdir) / "report.json").read_text(encoding="utf-8"))
            self.assertFalse(payload["preflight"]["passed"])
            self.assertEqual(payload["tasks"], [])
