from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli.tests.provider_boundary_test_support import assert_provider_home_env, provider_home_env

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "command_execution_wave03_ab.py"
SPEC = importlib.util.spec_from_file_location("command_execution_wave03_ab", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CommandExecutionWave03AbTest(unittest.TestCase):
    def test_build_parser_defaults_match_wave03_baseline(self) -> None:
        args = MODULE.build_parser().parse_args([])
        self.assertEqual(args.model, "gpt-5.4")
        self.assertEqual(args.reasoning_effort, "xhigh")
        self.assertEqual(args.agenthub_config_mode, "home")
        self.assertEqual(args.agenthub_interaction_profile, "codex_openai")
        self.assertEqual(args.codex_config_mode, "home")
        self.assertFalse(args.dry_run)

    def test_default_codex_provider_id_keeps_openai_for_official_and_proxy_urls(self) -> None:
        self.assertEqual(
            MODULE._default_codex_provider_id("https://relay.example/v1"), "openai-relay"
        )
        self.assertEqual(MODULE._default_codex_provider_id("https://api.openai.com/v1"), "openai")
        self.assertEqual(
            MODULE._default_codex_provider_id("https://example.test/v1"), "openai-relay"
        )

    def test_build_commands_include_expected_flags(self) -> None:
        agenthub_command = MODULE._build_agenthub_command(
            prompt="do work", main_path=Path("/tmp/main.py")
        )
        codex_command = MODULE._build_codex_command(
            prompt="do work",
            workspace=Path("/tmp/work"),
            model="gpt-5.4",
            reasoning_effort="high",
        )
        self.assertEqual(agenthub_command[0], sys.executable)
        self.assertIn("--headless", agenthub_command)
        self.assertIn("--json", agenthub_command)
        self.assertEqual(agenthub_command[-2:], ["--prompt", "do work"])
        self.assertEqual(codex_command[:3], ["codex", "exec", "--json"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", codex_command)
        self.assertIn("-C", codex_command)
        self.assertIn("/tmp/work", codex_command)
        self.assertEqual(codex_command[-1], "do work")

    def test_parse_agenthub_output_returns_stable_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parsed = MODULE._parse_agenthub_output(Path(tmpdir) / "missing.json")
        self.assertEqual(parsed["assistant_text"], "")
        self.assertEqual(parsed["tool_event_count"], 0)
        self.assertEqual(parsed["tool_names"], [])
        self.assertEqual(parsed["turn_event_count"], 0)
        self.assertEqual(parsed["response_item_count"], 0)

    def test_parse_agenthub_output_reads_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stdout.json"
            path.write_text(
                json.dumps(
                    {
                        "assistant_text": "done",
                        "commentary_text": "working",
                        "tool_events": [{"name": "exec_command"}, {"name": "write_stdin"}],
                        "turn_events": [{"type": "turn.started"}],
                        "response_items": [{"type": "reasoning"}, {"type": "message"}],
                        "status": {"thread_id": "t1"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            parsed = MODULE._parse_agenthub_output(path)
        self.assertEqual(parsed["assistant_text"], "done")
        self.assertEqual(parsed["commentary_text"], "working")
        self.assertEqual(parsed["tool_event_count"], 2)
        self.assertEqual(parsed["tool_names"], ["exec_command", "write_stdin"])
        self.assertEqual(parsed["turn_event_count"], 1)
        self.assertEqual(parsed["response_item_count"], 2)
        self.assertEqual(parsed["status"]["thread_id"], "t1")

    def test_parse_codex_output_reads_thread_counts_and_last_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stdout.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "thread.started", "thread_id": "abc"}, ensure_ascii=False
                        ),
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {"type": "command_execution", "command": "pwd"},
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {"type": "agent_message", "text": "final answer"},
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            parsed = MODULE._parse_codex_output(path)
        self.assertEqual(parsed["thread_id"], "abc")
        self.assertEqual(parsed["assistant_text"], "final answer")
        self.assertEqual(parsed["item_counts"]["command_execution"], 1)
        self.assertEqual(parsed["completed_item_counts"]["agent_message"], 1)

    def test_project_local_config_writes_interaction_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path, auth_path = MODULE._build_agenthub_project_local_config(
                project_root=Path(tmpdir),
                api_key="secret",
                provider_id="openai",
                model="gpt-5.4",
                reasoning_effort="high",
                openai_base_url="https://relay.example/v1",
                interaction_profile="codex_openai",
            )
            config_text = config_path.read_text(encoding="utf-8")
            auth_payload = json.loads(auth_path.read_text(encoding="utf-8"))
        self.assertIn('model_provider = "openai"', config_text)
        self.assertIn("[model_providers.openai]", config_text)
        self.assertIn('provider = "openai"', config_text)
        self.assertIn('interaction_profile = "codex_openai"', config_text)
        self.assertEqual(auth_payload["OPENAI_API_KEY"], "secret")

    def test_main_dry_run_writes_report_summary_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = MODULE.main(
                    [
                        "--dry-run",
                        "--json",
                        "--out-dir",
                        tmpdir,
                        "--codex-config-mode",
                        "ephemeral",
                        "--agenthub-config-mode",
                        "project_local",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema_version"], "command_execution_wave03_ab_v2")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["agenthub_config_mode"], "project_local")
            self.assertEqual(payload["codex_config_mode"], "ephemeral")
            self.assertEqual(payload["agenthub_interaction_profile"], "codex_openai")
            self.assertIn("summary_json", payload["log_manifest"])
            self.assertTrue((Path(tmpdir) / "report.json").exists())
            self.assertTrue((Path(tmpdir) / "summary.json").exists())
            self.assertTrue((Path(tmpdir) / "summary.md").exists())
            self.assertTrue((Path(tmpdir) / "commands.txt").exists())
            self.assertEqual(
                payload["systems"]["agenthub"]["workspace"],
                str(Path(tmpdir) / "agenthub_project" / "workdir"),
            )

    def test_main_project_local_pins_provider_home_and_clears_stale_agent_cli_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with (
                mock.patch("sys.stdout", stdout),
                mock.patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "from-env",
                        "AGENT_CLI_HOME": "/tmp/stale-agent-cli-home",
                        **provider_home_env("/tmp/stale-provider-home"),
                        "AGENTHUB_STARTUP_CWD": "/tmp/stale-startup-cwd",
                    },
                    clear=False,
                ),
            ):
                exit_code = MODULE.main(
                    [
                        "--dry-run",
                        "--json",
                        "--out-dir",
                        tmpdir,
                        "--codex-config-mode",
                        "ephemeral",
                        "--agenthub-config-mode",
                        "project_local",
                    ]
                )
            self.assertEqual(exit_code, 0)
            invocation = json.loads(
                (Path(tmpdir) / "agenthub.invocation.json").read_text(encoding="utf-8")
            )
            expected_workspace = Path(tmpdir) / "agenthub_project" / "workdir"
            expected_provider_home = Path(tmpdir) / "agenthub_project" / ".config"
            self.assertEqual(invocation["cwd"], str(MODULE.CLI_ROOT))
            self.assertEqual(invocation["env"]["AGENTHUB_STARTUP_CWD"], str(expected_workspace))
            assert_provider_home_env(invocation["env"], expected_provider_home)
            self.assertNotIn("AGENT_CLI_HOME", invocation["env"])

    def test_load_api_key_prefers_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "auth.json"
            auth_path.write_text(json.dumps({"OPENAI_API_KEY": "from-file"}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}, clear=False):
                value = MODULE._load_api_key(auth_path, "OPENAI_API_KEY")
        self.assertEqual(value, "from-env")
