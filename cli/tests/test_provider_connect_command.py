from __future__ import annotations

import io
import json
import shlex
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.main import main
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command
from cli.agent_cli.slash_parser import parse_slash_invocation


def _parse_args(arg_text: str):
    tokens = shlex.split(str(arg_text or "").strip()) if str(arg_text or "").strip() else []
    positionals: list[str] = []
    options: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key = token[2:]
            value: object = True
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                value = tokens[index + 1]
                index += 1
            options[key] = value
        else:
            positionals.append(token)
        index += 1
    return positionals, options


def _runtime_stub(cwd: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        _parse_args=_parse_args,
        cwd=str(cwd or Path.cwd()),
        agent=SimpleNamespace(provider_status=lambda: {}),
    )


def _switch_disabled_result(exc: Exception):
    return str(exc), []


def test_connect_rejects_positionals_with_usage() -> None:
    runtime = _runtime_stub()
    text, events = handle_provider_command(
        runtime,
        name="connect",
        arg_text="relay_openai_proxy",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])
    assert events == []
    assert text.startswith("Usage: /connect")


def test_connect_missing_args_returns_next_action() -> None:
    runtime = _runtime_stub()
    text, events = handle_provider_command(
        runtime,
        name="connect",
        arg_text="--provider relay_openai_proxy --model gpt-5.4",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])
    assert events == []
    assert "connect summary" in text
    assert "provider_name=relay_openai_proxy" in text
    assert "model=gpt-5.4" in text
    assert "auth_mode=-" in text
    assert "write_scope=user" in text
    assert "missing_args=base-url,auth-mode" in text
    assert (
        "next_action=/connect provider relay_openai_proxy model gpt-5.4 base-url <url> "
        "auth-mode <mode> api-key-env <ENV> user"
    ) in text


def test_connect_official_openai_defaults_auth_without_base_url() -> None:
    runtime = _runtime_stub()
    text, events = handle_provider_command(
        runtime,
        name="connect",
        arg_text="--provider openai --model gpt-5.4 --check",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])
    assert events == []
    assert "provider_name=openai" in text
    assert "model=gpt-5.4" in text
    assert "base_url=-" in text
    assert "auth_mode=api_key" in text
    assert "write_scope=user" in text
    assert "check_only=true" in text
    assert "connect_persisted=false" in text
    assert "missing_args=" not in text


def test_connect_check_mode_does_not_persist() -> None:
    with TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / ".agent_cli" / "config.toml"
        runtime = _runtime_stub()
        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", return_value=target):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text=(
                    "--provider relay_openai_proxy --model gpt-5.4 --base-url https://relay.example/v1 "
                    "--auth-mode api_key --api-key-env OPENAI_API_KEY --check"
                ),
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
    assert events == []
    assert "check_only=true" in text
    assert "provider_name=relay_openai_proxy" in text
    assert "model=gpt-5.4" in text
    assert "auth_mode=api_key" in text
    assert "write_scope=user" in text
    assert "next_action=run without check to persist" in text
    assert not target.exists()


def test_connect_persists_user_scope_config_with_typed_auth() -> None:
    with TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / ".agent_cli" / "config.toml"
        runtime = _runtime_stub()
        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", return_value=target):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text=(
                    "--provider relay_openai_proxy --model gpt-5.4 --base-url https://relay.example/v1 "
                    "--auth-mode api_key --api-key-env OPENAI_API_KEY --write user"
                ),
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        payload = tomllib.loads(target.read_text(encoding="utf-8"))
    assert events == []
    assert "connect_persisted=true" in text
    assert "provider_name=relay_openai_proxy" in text
    assert "model=gpt-5.4" in text
    assert "auth_mode=api_key" in text
    assert "write_scope=user" in text
    assert "next_action=/provider verbose" in text
    assert payload["default_provider_profile"] == "relay_openai_proxy_relay_example_v1"
    assert payload["model_provider"] == "relay_openai_proxy"
    assert payload["model"] == "gpt-5.4"
    provider = payload["model_providers"]["relay_openai_proxy"]
    assert provider["base_url"] == "https://relay.example/v1"
    assert provider["auth_mode"] == "api_key"
    assert provider["api_key_env"] == "OPENAI_API_KEY"
    profile = payload["provider_profiles"]["relay_openai_proxy_relay_example_v1"]
    assert profile["provider"] == "relay_openai_proxy"
    assert profile["model"] == "gpt-5.4"
    assert profile["base_url"] == "https://relay.example/v1"
    assert profile["auth_mode"] == "api_key"
    assert profile["api_key_env"] == "OPENAI_API_KEY"
    assert "auth" not in provider or provider.get("auth", {}).get("env_var") == "OPENAI_API_KEY"


def test_connect_persists_anthropic_defaults_without_base_url() -> None:
    with TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / ".agent_cli" / "config.toml"
        runtime = _runtime_stub()
        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", return_value=target):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text="--provider anthropic --model claude-sonnet-4-6 --write user",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        payload = tomllib.loads(target.read_text(encoding="utf-8"))
    assert events == []
    assert "connect_persisted=true" in text
    assert "provider_name=anthropic" in text
    assert "model=claude-sonnet-4-6" in text
    assert "auth_mode=api_key" in text
    assert "write_scope=user" in text
    assert payload["default_provider_profile"] == "anthropic_main"
    assert payload["model_provider"] == "anthropic"
    assert payload["model"] == "claude-sonnet-4-6"
    provider = payload["model_providers"]["anthropic"]
    assert "base_url" not in provider
    assert provider["auth_mode"] == "api_key"
    assert provider["api_key_env"] == "ANTHROPIC_API_KEY"
    profile = payload["provider_profiles"]["anthropic_main"]
    assert profile["provider"] == "anthropic"
    assert profile["model"] == "claude-sonnet-4-6"
    assert profile["auth_mode"] == "api_key"
    assert profile["api_key_env"] == "ANTHROPIC_API_KEY"


def test_connect_project_scope_splits_private_provider_fields_to_user_config() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_target = root / ".agent_cli" / "config.toml"
        user_target = root / "home" / ".agent_cli" / "config.toml"
        runtime = _runtime_stub()

        def _resolve_path(_runtime, scope: str) -> Path:
            return user_target if scope == "user" else project_target

        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", side_effect=_resolve_path):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text=(
                    "--provider openai --model gpt-5.4 --base-url https://relay03.gaccode.com/codex/v1 "
                    "--auth-mode api_key --api-key-env OPENAI_API_KEY --write project"
                ),
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])

        project_payload = tomllib.loads(project_target.read_text(encoding="utf-8"))
        user_payload = tomllib.loads(user_target.read_text(encoding="utf-8"))

    assert events == []
    assert "connect_persisted=true" in text
    assert "write_scope=project" in text
    assert f"config_path={project_target}" in text
    assert f"user_config_path={user_target}" in text
    assert project_payload["provider_profile"] == "openai_relay03_gaccode_com_codex_v1"
    assert project_payload["model"] == "gpt-5.4"
    project_provider = project_payload.get("model_providers", {}).get("openai", {})
    assert "model_provider" not in project_payload
    assert "models" not in project_payload
    assert "base_url" not in project_provider
    assert "auth_mode" not in project_provider
    assert "api_key_env" not in project_provider
    user_provider = user_payload["model_providers"]["openai"]
    assert user_provider["base_url"] == "https://relay03.gaccode.com/codex/v1"
    assert user_provider["auth_mode"] == "api_key"
    assert user_provider["api_key_env"] == "OPENAI_API_KEY"
    profile = user_payload["provider_profiles"]["openai_relay03_gaccode_com_codex_v1"]
    assert profile["provider"] == "openai"
    assert profile["model"] == "gpt-5.4"
    assert profile["base_url"] == "https://relay03.gaccode.com/codex/v1"
    assert profile["auth_mode"] == "api_key"
    assert profile["api_key_env"] == "OPENAI_API_KEY"
    assert "model_provider" not in user_payload
    assert "model" not in user_payload


def test_connect_project_scope_rewrites_legacy_private_provider_fields_out_of_project_config() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_target = root / ".agent_cli" / "config.toml"
        user_target = root / "home" / ".agent_cli" / "config.toml"
        project_target.parent.mkdir(parents=True, exist_ok=True)
        project_target.write_text(
            "\n".join(
                [
                    'provider_profile = "openai_main"',
                    'model = "gpt-4o"',
                    "[model_providers.openai]",
                    'base_url = "https://old.example/v1"',
                    'auth_mode = "api_key"',
                    'api_key_env = "OLD_OPENAI_API_KEY"',
                    'wire_api = "responses"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        runtime = _runtime_stub()

        def _resolve_path(_runtime, scope: str) -> Path:
            return user_target if scope == "user" else project_target

        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", side_effect=_resolve_path):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text="--provider openai --model gpt-5.4 --write project",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])

        project_payload = tomllib.loads(project_target.read_text(encoding="utf-8"))
        user_payload = tomllib.loads(user_target.read_text(encoding="utf-8"))

    assert events == []
    assert "connect_persisted=true" in text
    project_provider = project_payload["model_providers"]["openai"]
    assert project_payload["provider_profile"] == "openai_main"
    assert project_payload["model"] == "gpt-5.4"
    assert project_provider["wire_api"] == "responses"
    assert "base_url" not in project_provider
    assert "auth_mode" not in project_provider
    assert "api_key_env" not in project_provider
    user_provider = user_payload["model_providers"]["openai"]
    assert user_provider["auth_mode"] == "api_key"
    assert user_provider["api_key_env"] == "OPENAI_API_KEY"
    profile = user_payload["provider_profiles"]["openai_main"]
    assert profile["provider"] == "openai"
    assert profile["model"] == "gpt-5.4"
    assert profile["auth_mode"] == "api_key"
    assert profile["api_key_env"] == "OPENAI_API_KEY"


def test_connect_slash_invocation_native_path_does_not_require_cli_parse_args() -> None:
    with TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / ".agent_cli" / "config.toml"
        runtime = SimpleNamespace(cwd=str(Path(temp_dir)), agent=SimpleNamespace(provider_status=lambda: {}))
        with patch("cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path", return_value=target):
            text, events = handle_provider_command(
                runtime,
                name="connect",
                arg_text="",
                slash_invocation=parse_slash_invocation("/connect provider anthropic model claude-sonnet-4-6 user"),
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        payload = tomllib.loads(target.read_text(encoding="utf-8"))

    assert events == []
    assert "connect_persisted=true" in text
    assert "provider_name=anthropic" in text
    assert "model=claude-sonnet-4-6" in text
    assert "write_scope=user" in text
    assert payload["model_provider"] == "anthropic"
    assert payload["model"] == "claude-sonnet-4-6"


def test_connect_project_scope_uses_project_root_provider_path_for_nested_cwd() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "apps" / "api"
        workspace.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text("gitdir: here\n", encoding="utf-8")

        text, events = handle_provider_command(
            _runtime_stub(workspace),
            name="connect",
            arg_text="--provider openai --model gpt-5.4 --write project --check",
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])

    assert events == []
    assert "write_scope=project" in text
    assert f"config_path={root / '.agent_cli' / 'config.toml'}" in text


def test_connect_user_scope_uses_user_provider_config_helper() -> None:
    runtime = _runtime_stub()
    with patch(
        "cli.agent_cli.runtime_core.provider_commands.resolve_user_provider_config_path",
        return_value=Path("/tmp/user-scope-config.toml"),
    ):
        text, events = handle_provider_command(
            runtime,
            name="connect",
            arg_text="--provider openai --model gpt-5.4 --check",
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])

    assert events == []
    assert "write_scope=user" in text
    assert "config_path=/tmp/user-scope-config.toml" in text


def test_model_slash_invocation_native_path_does_not_require_cli_parse_args() -> None:
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            provider_status=lambda: {
                "provider_model": "gpt-5.4",
                "model_key": "gpt_54",
                "provider_reasoning_effort": "medium",
                "session_line": "openai | gpt-5.4",
            }
        ),
        configure_model_selection=lambda **kwargs: {
            "provider_display_label": "openai | gpt-5.4-mini",
            "provider_label": "openai | gpt-5.4-mini",
            "provider_planner": "openai_responses",
            "provider_source": "user_config",
            "provider_ready": "true",
            "provider_reasoning_effort": kwargs.get("reasoning_effort") or "high",
            "provider_selection_path": "/tmp/user-config.toml",
        },
    )

    text, events = handle_provider_command(
        runtime,
        name="model",
        arg_text="",
        slash_invocation=parse_slash_invocation("/model gpt_54 high user"),
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert "updated user default model=gpt_54, reasoning_effort=high" in text
    assert "current_reasoning_effort=high" in text
    assert "write_scope=user" in text


def test_connect_headless_json_output_keeps_connect_summary_shape() -> None:
    runtime = AgentCliRuntime()
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = main(
        [
            "--headless",
            "--prompt",
            "/connect --provider relay_openai_proxy --model gpt-5.4 --base-url https://relay.example/v1 --auth-mode api_key --api-key-env OPENAI_API_KEY --check",
            "--json",
        ],
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert "connect summary" in payload["assistant_text"]
    assert "provider_name=relay_openai_proxy" in payload["assistant_text"]
    assert "model=gpt-5.4" in payload["assistant_text"]
    assert "auth_mode=api_key" in payload["assistant_text"]
    assert "write_scope=user" in payload["assistant_text"]


def test_connect_headless_stream_json_keeps_turn_and_thread_events() -> None:
    runtime = AgentCliRuntime()
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = main(
        [
            "--headless",
            "--prompt",
            "/connect --provider relay_openai_proxy --model gpt-5.4 --base-url https://relay.example/v1 --auth-mode api_key --api-key-env OPENAI_API_KEY --check",
            "--jsonl",
        ],
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert code == 0
    assert stderr.getvalue() == ""
    assert lines[0]["type"] == "thread.started"
    assert any(line.get("type") == "turn.started" for line in lines)
    assert any(
        line.get("type") == "item.completed" and str((line.get("item") or {}).get("type") or "") == "agent_message"
        for line in lines
    )
    assert any(line.get("type") == "turn.completed" for line in lines)
