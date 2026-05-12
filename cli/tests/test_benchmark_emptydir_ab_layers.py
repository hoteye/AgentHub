from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli.tests.provider_boundary_test_support import assert_provider_home_env, provider_home_env

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "benchmark_emptydir_ab.py"
SPEC = importlib.util.spec_from_file_location("benchmark_emptydir_ab", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class BenchmarkEmptyDirLayersTest(unittest.TestCase):
    def test_parse_args_defaults_pin_codex_openai_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "prompt.txt"
            prompt_path.write_text("hello", encoding="utf-8")
            with mock.patch.object(
                sys,
                "argv",
                [
                    "benchmark_emptydir_ab.py",
                    "--prompt-file",
                    str(prompt_path),
                ],
            ):
                args = MODULE.parse_args()
        self.assertEqual(args.agenthub_interaction_profile, "codex_openai")

    def test_default_codex_provider_id_uses_safe_relay_name_for_non_official_base_url(self) -> None:
        self.assertEqual(
            MODULE._default_codex_provider_id("https://relay.example/v1"), "openai-relay"
        )
        self.assertEqual(MODULE._default_codex_provider_id("https://api.openai.com/v1"), "openai")

    def test_codex_command_uses_explicit_compiled_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fake_bin = tmp_path / "codex"
            fake_bin.write_text("", encoding="utf-8")
            expected_result = MODULE.CommandResult(
                name="codex",
                command=[],
                cwd=str(tmp_path),
                exit_code=0,
                elapsed_seconds=0.1,
                timed_out=False,
                started_at="2026-04-19T00:00:00+00:00",
                ended_at="2026-04-19T00:00:00+00:00",
                stdout_path=str(tmp_path / "out"),
                stderr_path=str(tmp_path / "err"),
            )
            with mock.patch.object(
                MODULE, "_run_command", return_value=expected_result
            ) as run_command:
                MODULE._codex_command(
                    prompt="hello",
                    workspace=tmp_path,
                    env={"BENCH_MODEL": "gpt-5.4", "BENCH_REASONING_EFFORT": "high"},
                    timeout_seconds=30,
                    out_dir=tmp_path,
                    codex_bin=fake_bin,
                )
            command = run_command.call_args.kwargs["command"]
            self.assertEqual(command[0], str(fake_bin))

    def test_agenthub_command_runs_from_cli_root_not_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            expected_result = MODULE.CommandResult(
                name="agenthub",
                command=[],
                cwd=str(tmp_path),
                exit_code=0,
                elapsed_seconds=0.1,
                timed_out=False,
                started_at="2026-04-19T00:00:00+00:00",
                ended_at="2026-04-19T00:00:00+00:00",
                stdout_path=str(tmp_path / "out"),
                stderr_path=str(tmp_path / "err"),
            )
            with mock.patch.object(
                MODULE, "_run_command", return_value=expected_result
            ) as run_command:
                MODULE._agenthub_command(
                    prompt="hello",
                    workspace=tmp_path / "workspace",
                    env={"AGENTHUB_STARTUP_CWD": str(tmp_path / "workspace")},
                    timeout_seconds=30,
                    out_dir=tmp_path,
                    main_path=tmp_path / "main.py",
                    network_access="disabled",
                )
            self.assertEqual(run_command.call_args.kwargs["cwd"], MODULE.REPO_ROOT)
            self.assertIn("--network-access", run_command.call_args.kwargs["command"])
            self.assertIn("disabled", run_command.call_args.kwargs["command"])

    def test_build_agenthub_env_clears_stale_home_and_sets_provider_home(self) -> None:
        env = MODULE._build_agenthub_env(
            common_env={
                "OPENAI_API_KEY": "secret",
                "AGENT_CLI_HOME": "/tmp/stale-agent-cli-home",
                **provider_home_env("/tmp/stale-provider-home"),
                "AGENTHUB_STARTUP_CWD": "/tmp/stale-startup-cwd",
            },
            provider="openai",
            model="gpt-5.4",
            reasoning_effort="high",
            openai_base_url="https://relay.example/v1",
            provider_home=Path("/tmp/provider-home"),
            startup_cwd=Path("/tmp/workspace"),
            debug_log_dir=Path("/tmp/debug-logs"),
        )
        self.assertNotIn("AGENT_CLI_HOME", env)
        assert_provider_home_env(env, "/tmp/provider-home")
        self.assertEqual(env["AGENTHUB_STARTUP_CWD"], "/tmp/workspace")
        self.assertEqual(env["AGENTHUB_DEBUG_LOG_DIR"], "/tmp/debug-logs")

    def test_build_agenthub_home_copies_codex_skills_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_home = tmp_path / "codex_home"
            target_home = tmp_path / "agenthub_home"
            skill_dir = source_home / "skills" / ".system" / "demo"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo\ndescription: demo skill\n---\n",
                encoding="utf-8",
            )

            MODULE._build_agenthub_home(agenthub_home=target_home, codex_skills_home=source_home)

            copied = target_home / "skills" / ".system" / "demo" / "SKILL.md"
            self.assertTrue(copied.exists())
            self.assertIn("description: demo skill", copied.read_text(encoding="utf-8"))

    def test_request_raw_and_tool_schema_layers_surface_schema_diffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            shared_instructions = "same instructions"
            agenthub_request = {
                "model": "gpt-5.4",
                "instructions": shared_instructions,
                "input": [{"type": "message", "role": "user"}],
                "prompt_cache_key": "thread_123",
                "reasoning": {"effort": "high", "summary": "auto"},
                "include": ["reasoning.encrypted_content"],
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "run",
                        "parameters": {"type": "object"},
                    },
                    {"type": "web_search", "external_web_access": True},
                    {
                        "type": "function",
                        "name": "apply_patch",
                        "description": "patch",
                        "parameters": {"type": "object"},
                    },
                ],
            }
            codex_request = {
                "model": "gpt-5.4",
                "instructions": shared_instructions,
                "input": [{"type": "message", "role": "user"}],
                "prompt_cache_key": "thread_123",
                "reasoning": {"effort": "high", "summary": "auto"},
                "include": ["reasoning.encrypted_content"],
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "run",
                        "parameters": {"type": "object"},
                    },
                    {"type": "web_search", "external_web_access": False},
                ],
            }
            agenthub_llm_io = tmp_path / "agenthub" / "llm_io.jsonl"
            codex_llm_io = tmp_path / "codex" / "llm_io.jsonl"
            _write_jsonl(
                agenthub_llm_io,
                [{"stage": "responses.send.request_raw", "payload": {"request": agenthub_request}}],
            )
            _write_jsonl(
                codex_llm_io,
                [{"stage": "stream_responses_api.request.raw", "payload": codex_request}],
            )

            request_raw_layer = MODULE._build_request_raw_layer(
                agenthub_llm_io_path=agenthub_llm_io,
                codex_llm_io_path=codex_llm_io,
            )
            tool_schema_layer = MODULE._build_tool_schema_layer(request_raw_layer)

            self.assertTrue(request_raw_layer["summary"]["instructions_equal"])
            self.assertTrue(request_raw_layer["summary"]["prompt_cache_key_present_equal"])
            self.assertTrue(request_raw_layer["summary"]["prompt_cache_key_shape_equal"])
            self.assertFalse(request_raw_layer["summary"]["tools_equal"])
            self.assertEqual(tool_schema_layer["summary"]["agenthub_only"], ["apply_patch"])
            self.assertEqual(
                tool_schema_layer["summary"]["shared_different_schema"], ["web_search"]
            )

    def test_request_raw_layer_ignores_agenthub_transport_headers_and_compares_prompt_cache_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            agenthub_llm_io = tmp_path / "agenthub" / "llm_io.jsonl"
            codex_llm_io = tmp_path / "codex" / "llm_io.jsonl"
            _write_jsonl(
                agenthub_llm_io,
                [
                    {
                        "stage": "responses.send.request_raw",
                        "payload": {
                            "request": {
                                "model": "gpt-5.4",
                                "instructions": "same instructions",
                                "input": [{"type": "message", "role": "user"}],
                                "prompt_cache_key": "0123456789abcdef0123456789abcdef",
                                "extra_headers": {"session_id": "0123456789abcdef0123456789abcdef"},
                            }
                        },
                    }
                ],
            )
            _write_jsonl(
                codex_llm_io,
                [
                    {
                        "stage": "stream_responses_api.request.raw",
                        "payload": {
                            "model": "gpt-5.4",
                            "instructions": "same instructions",
                            "input": [{"type": "message", "role": "user"}],
                            "prompt_cache_key": "019da99c-865c-7f23-8ddf-068d5d0b02c3",
                        },
                    }
                ],
            )

            request_raw_layer = MODULE._build_request_raw_layer(
                agenthub_llm_io_path=agenthub_llm_io,
                codex_llm_io_path=codex_llm_io,
            )

            self.assertTrue(request_raw_layer["summary"]["instructions_equal"])
            self.assertTrue(request_raw_layer["summary"]["input_equal"])
            self.assertTrue(request_raw_layer["summary"]["prompt_cache_key_present_equal"])
            self.assertFalse(request_raw_layer["summary"]["prompt_cache_key_shape_equal"])
            self.assertNotIn("extra_headers_equal", request_raw_layer["summary"])

    def test_request_raw_layer_skips_agenthub_probe_and_selects_first_tool_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            agenthub_llm_io = tmp_path / "agenthub" / "llm_io.jsonl"
            codex_llm_io = tmp_path / "codex" / "llm_io.jsonl"
            _write_jsonl(
                agenthub_llm_io,
                [
                    {
                        "stage": "responses.send.request_raw",
                        "payload": {
                            "request": {
                                "model": "gpt-5.4",
                                "instructions": "same instructions",
                                "input": [{"type": "message", "role": "user"}],
                                "tools": [],
                            }
                        },
                    },
                    {
                        "stage": "responses.send.request_raw",
                        "payload": {
                            "request": {
                                "model": "gpt-5.4",
                                "instructions": "same instructions",
                                "input": [
                                    {"type": "message", "role": "developer"},
                                    {"type": "message", "role": "user"},
                                    {"type": "message", "role": "user"},
                                ],
                                "tools": [{"type": "function", "name": "exec_command"}],
                                "prompt_cache_key": "019da9c7-b4fc-7763-879f-4bd4ec66254c",
                            }
                        },
                    },
                    {
                        "stage": "responses.send.request_raw",
                        "payload": {
                            "request": {
                                "model": "gpt-5.4",
                                "instructions": "same instructions",
                                "input": [{"type": "message", "role": "assistant"}] * 8,
                                "tools": [{"type": "function", "name": "exec_command"}],
                                "prompt_cache_key": "019da9c7-b4fc-7763-879f-4bd4ec66254c",
                            }
                        },
                    },
                ],
            )
            _write_jsonl(
                codex_llm_io,
                [
                    {
                        "stage": "stream_responses_api.request.raw",
                        "payload": {
                            "model": "gpt-5.4",
                            "instructions": "same instructions",
                            "input": [
                                {"type": "message", "role": "developer"},
                                {"type": "message", "role": "user"},
                                {"type": "message", "role": "user"},
                            ],
                            "tools": [{"type": "function", "name": "exec_command"}],
                            "prompt_cache_key": "019da9c7-b4fc-7763-879f-4bd4ec66254c",
                        },
                    }
                ],
            )

            request_raw_layer = MODULE._build_request_raw_layer(
                agenthub_llm_io_path=agenthub_llm_io,
                codex_llm_io_path=codex_llm_io,
            )

            self.assertTrue(request_raw_layer["summary"]["input_equal"])
            self.assertTrue(request_raw_layer["summary"]["tools_equal"])
            self.assertTrue(request_raw_layer["summary"]["prompt_cache_key_present_equal"])
            self.assertTrue(request_raw_layer["summary"]["prompt_cache_key_shape_equal"])
            self.assertEqual(request_raw_layer["agenthub"]["candidate_count"], 3)
            self.assertEqual(request_raw_layer["agenthub"]["selected_candidate_index"], 2)

    def test_tool_call_chain_layer_pairs_agenthub_and_codex_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            agenthub_detail_path = tmp_path / "agenthub.detail.json"
            codex_detail_path = tmp_path / "codex.detail.json"
            codex_turn_actions_path = tmp_path / "codex.turn_actions.jsonl"
            agenthub_detail_path.write_text(
                json.dumps(
                    {
                        "tool_events": [
                            {
                                "name": "exec_command",
                                "ok": True,
                                "payload": {
                                    "call_id": "call_agent_1",
                                    "command": "pwd",
                                    "stdout": "/tmp/demo\n",
                                    "provider_raw_item": {
                                        "name": "exec_command",
                                        "arguments": '{"cmd":"pwd"}',
                                    },
                                },
                            },
                            {
                                "name": "apply_patch",
                                "ok": True,
                                "payload": {
                                    "call_id": "call_agent_2",
                                    "provider_raw_item": {
                                        "name": "apply_patch",
                                        "arguments": "*** Begin Patch",
                                    },
                                },
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            codex_detail_path.write_text(
                json.dumps({"events": []}, ensure_ascii=False), encoding="utf-8"
            )
            _write_jsonl(
                codex_turn_actions_path,
                [
                    {
                        "stage": "tool_loop.output_item.routed_tool_call",
                        "payload": {
                            "tool_call": {
                                "tool_name": "exec_command",
                                "call_id": "call_codex_1",
                                "payload_preview": '{"cmd":"pwd"}',
                            }
                        },
                    },
                    {
                        "stage": "tool_loop.in_flight.response_input",
                        "payload": {
                            "response_input_item": {
                                "call_id": "call_codex_1",
                                "success": True,
                                "preview": "Output: /tmp/demo",
                            }
                        },
                    },
                ],
            )

            layer = MODULE._build_tool_call_chain_layer(
                agenthub_detail_path=agenthub_detail_path,
                codex_detail_path=codex_detail_path,
                codex_turn_actions_path=codex_turn_actions_path,
            )

            self.assertEqual(
                layer["summary"]["agenthub_tool_names"], ["exec_command", "apply_patch"]
            )
            self.assertEqual(layer["summary"]["codex_tool_names"], ["exec_command"])
            self.assertFalse(layer["summary"]["tool_name_sequence_equal"])

    def test_workspace_side_effects_layer_distinguishes_hidden_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            agenthub_workspace = tmp_path / "agenthub"
            codex_workspace = tmp_path / "codex"
            (agenthub_workspace / "main.py").parent.mkdir(parents=True, exist_ok=True)
            (codex_workspace / "main.py").parent.mkdir(parents=True, exist_ok=True)
            (agenthub_workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
            (codex_workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
            (codex_workspace / ".codex").mkdir(parents=True, exist_ok=True)
            (codex_workspace / ".codex" / "state.json").write_text("{}", encoding="utf-8")
            run_result = MODULE.CommandResult(
                name="demo",
                command=["true"],
                cwd=str(tmp_path),
                exit_code=0,
                elapsed_seconds=0.1,
                timed_out=False,
                started_at="2026-04-19T00:00:00+00:00",
                ended_at="2026-04-19T00:00:00+00:00",
                stdout_path=str(tmp_path / "stdout.log"),
                stderr_path=str(tmp_path / "stderr.log"),
            )

            layer = MODULE._build_workspace_side_effects_layer(
                agenthub_workspace=agenthub_workspace,
                codex_workspace=codex_workspace,
                agenthub_run=run_result,
                codex_run=run_result,
                agenthub_validation=None,
                codex_validation=None,
                agenthub_assistant_text="ok",
                codex_assistant_text="ok",
            )

            self.assertFalse(layer["summary"]["all_files_equal"])
            self.assertTrue(layer["summary"]["visible_files_equal"])
            self.assertEqual(layer["summary"]["codex_only_all_paths"], [".codex/state.json"])
