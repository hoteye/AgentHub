from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from cli.tests.provider_boundary_test_support import assert_provider_home_env

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "provider_two_turn_live_smoke.py"
SPEC = importlib.util.spec_from_file_location("provider_two_turn_live_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_default_cases_cover_openai_and_anthropic() -> None:
    cases = MODULE.default_cases()

    assert [case.label for case in cases] == [
        "openai:gpt_54",
        "anthropic:claude_sonnet_46",
    ]


def test_provider_case_env_overrides_supports_provider_home() -> None:
    env = MODULE.ProviderCase(provider="anthropic", model="claude_sonnet_46").env_overrides(
        provider_home="/tmp/provider-home"
    )

    assert env["AGENT_CLI_PROVIDER"] == "anthropic"
    assert env["AGENT_CLI_MODEL"] == "claude_sonnet_46"
    assert_provider_home_env(env, "/tmp/provider-home")


def test_evaluate_case_health_requires_second_turn_to_echo_token() -> None:
    payload = {
        "provider_runtime_state": "ready",
        "token": "AGENTHUB-LIVE-SMOKE-test",
        "turns": [
            {
                "assistant_text": "READY",
                "provider_used": True,
                "protocol_path_kind": "provider_loop",
                "tool_event_count": 0,
            },
            {
                "assistant_text": "AGENTHUB-LIVE-SMOKE-test",
                "provider_used": True,
                "protocol_path_kind": "provider_loop",
                "tool_event_count": 0,
            },
        ],
    }

    assert MODULE.evaluate_case_health(payload) == "ok"
    payload["turns"][1]["assistant_text"] = "wrong"
    assert MODULE.evaluate_case_health(payload) == "error"


def test_evaluate_case_health_rejects_degraded_fallback() -> None:
    payload = {
        "provider_runtime_state": "ready",
        "token": "token",
        "turns": [
            {
                "assistant_text": "READY",
                "provider_used": True,
                "protocol_path_kind": "provider_loop",
                "tool_event_count": 0,
            },
            {
                "assistant_text": "当前 provider 调用失败",
                "provider_used": True,
                "protocol_path_kind": "provider_degraded_fallback",
                "tool_event_count": 0,
            },
        ],
    }

    assert MODULE.evaluate_case_health(payload) == "error"


def test_common_worker_command_omits_provider_home_when_unset() -> None:
    command = MODULE._common_worker_command(
        MODULE.ProviderCase(provider="openai", model="gpt_54"),
        token="token",
        provider_home="",
    )

    assert "--provider-home" not in command


def test_run_case_subprocess_skips_bad_lines_before_json_payload() -> None:
    completed = CompletedProcess(
        args=["python"],
        returncode=0,
        stdout='\nnoise line\n{"provider":"openai","model":"gpt_54","health":"ok","wall_ms":321}\n',
        stderr="",
    )

    with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
        result = MODULE._run_case_subprocess(
            MODULE.ProviderCase(provider="openai", model="gpt_54"),
            token="token",
            timeout_seconds=5,
            provider_home="",
        )

    assert result["provider"] == "openai"
    assert result["model"] == "gpt_54"
    assert result["health"] == "ok"
    assert result["worker_wall_ms"] == 321


def test_main_dry_run_outputs_default_cases() -> None:
    stdout = io.StringIO()

    with mock.patch.object(
        MODULE,
        "resolve_effective_script_provider_home_dir",
        return_value=Path("/tmp/runtime-provider-home"),
    ):
        with mock.patch("sys.stdout", stdout):
            exit_code = MODULE.main(["--dry-run", "--json", "--run-id", "test"])

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["provider_home"] == "/tmp/runtime-provider-home"
    assert [case["provider"] for case in payload["cases"]] == ["openai", "anthropic"]
    assert payload["cases"][0]["token"] == "AGENTHUB-LIVE-SMOKE-test-openai-gpt-54"
