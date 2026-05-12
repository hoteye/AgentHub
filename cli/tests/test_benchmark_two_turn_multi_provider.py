from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from cli.scripts import benchmark_two_turn_output_helpers as output_helpers
from cli.tests.provider_boundary_test_support import assert_provider_home_env


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "benchmark_two_turn_multi_provider.py"
SPEC = importlib.util.spec_from_file_location("benchmark_two_turn_multi_provider", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summary_for_results_counts_cases_and_fastest_ok_case() -> None:
    summary = output_helpers.summary_for_results(
        [
            {
                "provider": "openai",
                "model": "gpt-5.4",
                "health": "ok",
                "orchestrator_wall_ms": 1000,
            },
            {
                "provider": "glm",
                "model": "glm-5",
                "health": "warning",
                "orchestrator_wall_ms": 1500,
            },
            {
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "health": "error",
                "orchestrator_wall_ms": 500,
            },
        ]
    )

    assert summary["cases"] == 3
    assert summary["ok"] == 1
    assert summary["warning"] == 1
    assert summary["error"] == 1
    assert summary["avg_case_wall_ms"] == 1000
    assert summary["fastest_ok_case"] == {
        "provider": "openai",
        "model": "gpt-5.4",
        "label": "openai:gpt-5.4",
        "orchestrator_wall_ms": 1000,
    }


def test_benchmark_case_env_overrides_omits_provider_home_when_unset() -> None:
    env = MODULE.BenchmarkCase(provider="openai", model="gpt-5.4").env_overrides()

    assert env == {
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt-5.4",
    }


def test_benchmark_case_env_overrides_enables_strict_isolation_when_provider_home_explicit() -> None:
    env = MODULE.BenchmarkCase(provider="openai", model="gpt-5.4").env_overrides(
        provider_home="/tmp/provider-home"
    )

    assert_provider_home_env(env, "/tmp/provider-home")


def test_common_worker_command_omits_provider_home_when_unset() -> None:
    command = MODULE._common_worker_command(
        MODULE.BenchmarkCase(provider="openai", model="gpt-5.4"),
        first_prompt="今天几号？",
        second_prompt="明天呢？",
        timezone_name="Asia/Shanghai",
        current_datetime="2026-04-14T10:00:00+08:00",
        provider_home="",
    )

    assert "--provider-home" not in command


def test_run_case_subprocess_skips_bad_lines_before_json_payload() -> None:
    case = MODULE.BenchmarkCase(provider="openai", model="gpt-5.4")
    completed = CompletedProcess(
        args=["python"],
        returncode=0,
        stdout='\nnoise line\n{"provider":"openai","model":"gpt-5.4","health":"ok","wall_ms":321}\n',
        stderr="",
    )

    with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
        result = MODULE._run_case_subprocess(
            case,
            first_prompt="今天几号？",
            second_prompt="明天呢？",
            timezone_name="Asia/Shanghai",
            current_datetime="2026-04-14T10:00:00+08:00",
            timeout_seconds=5.0,
            provider_home="/tmp/provider-home",
        )

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5.4"
    assert result["health"] == "ok"
    assert result["worker_wall_ms"] == 321
    assert "parse_error" not in result


def test_main_dry_run_uses_runtime_provider_home_without_env_override() -> None:
    stdout = io.StringIO()
    with mock.patch.object(
        MODULE,
        "resolve_effective_script_provider_home_dir",
        return_value=Path("/tmp/runtime-provider-home"),
    ):
        with mock.patch("sys.stdout", stdout):
            exit_code = MODULE.main(["--case", "openai:gpt-5.4", "--max-workers", "1", "--dry-run", "--json"])

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["provider_home"] == "/tmp/runtime-provider-home"
    assert payload["provider_home_override"] == ""
    assert payload["provider_home_source"] == "runtime_default"
    assert payload["cases"][0]["env"] == {
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt-5.4",
    }


def test_main_json_output_includes_structured_summary() -> None:
    stdout = io.StringIO()
    result = {
        "provider": "openai",
        "model": "gpt-5.4",
        "health": "ok",
        "provider_runtime_state": "ready",
        "orchestrator_wall_ms": 1200,
        "turns": [
            {"total_ms": 400, "expected_date_match": True, "assistant_preview": "今天是 2026-04-14"},
            {"total_ms": 500, "expected_date_match": True, "assistant_preview": "明天是 2026-04-15"},
        ],
    }

    with mock.patch.object(MODULE, "_run_case_subprocess", return_value=result):
        with mock.patch("sys.stdout", stdout):
            exit_code = MODULE.main(["--case", "openai:gpt-5.4", "--max-workers", "1", "--json"])

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["results"] == [result]
    assert payload["summary"]["cases"] == 1
    assert payload["summary"]["ok"] == 1
    assert payload["summary"]["warning"] == 0
    assert payload["summary"]["error"] == 0
    assert payload["summary"]["fastest_ok_case"]["label"] == "openai:gpt-5.4"
