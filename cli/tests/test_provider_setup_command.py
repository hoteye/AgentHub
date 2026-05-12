from __future__ import annotations

import json
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.runtime_core.setup_commands import handle_setup_command


def _runtime_stub(cwd: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        cwd=str(cwd or Path.cwd()),
        agent=SimpleNamespace(provider_status=lambda: {}),
    )


def test_setup_status_reports_unconfigured_when_no_provider_state_exists() -> None:
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=Path("/tmp/provider/config.toml"),
            auth_path=Path("/tmp/provider/auth.json"),
            config_exists=False,
            auth_exists=False,
        ),
        selected_config=None,
    )
    runtime = _runtime_stub()
    with patch(
        "cli.agent_cli.runtime_core.setup_commands.provider_module.load_provider_management_snapshot",
        return_value=snapshot,
    ):
        text, events = handle_setup_command(runtime, name="setup", arg_text="status") or ("", [])

    assert events == []
    assert "setup status" in text
    assert "state=unconfigured" in text
    assert "next_action=/setup" in text


def test_setup_without_args_returns_minimal_api_key_guide() -> None:
    runtime = _runtime_stub()

    text, events = handle_setup_command(runtime, name="setup", arg_text="") or ("", [])

    assert events == []
    assert "setup" in text
    assert "mode=api_key" in text
    assert "required=provider,api-key" in text


def test_setup_status_reports_hard_unavailable_provider_as_setup_needed() -> None:
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=Path("/tmp/provider/config.toml"),
            auth_path=Path("/tmp/provider/auth.json"),
            config_exists=True,
            auth_exists=True,
        ),
        selected_config=SimpleNamespace(
            provider_name="openai",
            model="gpt-5.4",
            auth_mode="api_key",
            api_key="sk-existing",
        ),
    )
    runtime = SimpleNamespace(
        cwd=str(Path.cwd()),
        agent=SimpleNamespace(
            provider_status=lambda: {
                "provider_status_state": "hard_unavailable",
                "provider_status_reason": "http_402",
                "provider_hard_unavailable": "true",
            }
        ),
    )

    with patch(
        "cli.agent_cli.runtime_core.setup_commands.provider_module.load_provider_management_snapshot",
        return_value=snapshot,
    ):
        text, events = handle_setup_command(runtime, name="setup", arg_text="status") or ("", [])

    assert events == []
    assert "state=hard_unavailable" in text
    assert "next_action=/setup provider openai api-key YOUR_API_KEY" in text


def test_setup_persists_user_config_and_auth_json_for_api_key_flow() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / ".agent_cli" / "config.toml"
        auth_path = root / ".agent_cli" / "auth.json"
        runtime = _runtime_stub(cwd=root)

        with (
            patch(
                "cli.agent_cli.runtime_core.setup_commands.resolve_private_provider_auth_write_path",
                return_value=auth_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path",
                return_value=config_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.setup_commands.provider_module.load_provider_catalog",
                return_value=SimpleNamespace(),
            ),
            patch(
                "cli.agent_cli.runtime_core.setup_commands.provider_module._default_model_entry",
                return_value=SimpleNamespace(model_id="gpt-5.4"),
            ),
        ):
            text, events = handle_setup_command(
                runtime,
                name="setup",
                arg_text="provider openai api-key sk-openai",
            ) or ("", [])

        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        auth_payload = json.loads(auth_path.read_text(encoding="utf-8"))

    assert events == []
    assert "connect_persisted=true" in text
    assert "auth_persisted=true" in text
    assert "auth_key=OPENAI_API_KEY" in text
    assert payload["default_provider_profile"] == "openai_main"
    assert payload["model_provider"] == "openai"
    assert payload["model"] == "gpt-5.4"
    assert payload["model_providers"]["openai"]["auth_mode"] == "api_key"
    assert payload["model_providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"
    profile = payload["provider_profiles"]["openai_main"]
    assert profile["provider"] == "openai"
    assert profile["model"] == "gpt-5.4"
    assert profile["auth_mode"] == "api_key"
    assert profile["api_key_env"] == "OPENAI_API_KEY"
    assert auth_payload["OPENAI_API_KEY"] == "sk-openai"


def test_setup_uses_builtin_default_model_for_known_provider_when_catalog_is_empty() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / ".agent_cli" / "config.toml"
        auth_path = root / ".agent_cli" / "auth.json"
        runtime = _runtime_stub(cwd=root)

        with (
            patch(
                "cli.agent_cli.runtime_core.setup_commands.resolve_private_provider_auth_write_path",
                return_value=auth_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path",
                return_value=config_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.setup_commands.provider_module.load_provider_catalog",
                side_effect=RuntimeError("catalog unavailable"),
            ),
        ):
            text, _ = handle_setup_command(
                runtime,
                name="setup",
                arg_text="provider openai api-key sk-openai",
            ) or ("", [])

        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert "connect_persisted=true" in text
    assert payload["default_provider_profile"] == "openai_main"
    assert payload["model"] == "gpt-5.4"


def test_setup_surface_syntax_accepts_optional_base_url() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / ".agent_cli" / "config.toml"
        auth_path = root / ".agent_cli" / "auth.json"
        runtime = _runtime_stub(cwd=root)

        with (
            patch(
                "cli.agent_cli.runtime_core.setup_commands.resolve_private_provider_auth_write_path",
                return_value=auth_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path",
                return_value=config_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.setup_commands.provider_module.load_provider_catalog",
                return_value=SimpleNamespace(),
            ),
            patch(
                "cli.agent_cli.runtime_core.setup_commands.provider_module._default_model_entry",
                return_value=SimpleNamespace(model_id="gpt-5.4"),
            ),
        ):
            text, _ = handle_setup_command(
                runtime,
                name="setup",
                arg_text="provider openai api-key sk-openai base-url https://example.test/v1",
            ) or ("", [])

        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert "connect_persisted=true" in text
    assert payload["model_providers"]["openai"]["base_url"] == "https://example.test/v1"
    profile = payload["provider_profiles"]["openai_example_test_v1"]
    assert profile["provider"] == "openai"
    assert profile["model"] == "gpt-5.4"
    assert profile["base_url"] == "https://example.test/v1"


def test_setup_surface_syntax_accepts_optional_model() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / ".agent_cli" / "config.toml"
        auth_path = root / ".agent_cli" / "auth.json"
        runtime = _runtime_stub(cwd=root)

        with (
            patch(
                "cli.agent_cli.runtime_core.setup_commands.resolve_private_provider_auth_write_path",
                return_value=auth_path,
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands._resolve_connect_write_path",
                return_value=config_path,
            ),
        ):
            text, events = handle_setup_command(
                runtime,
                name="setup",
                arg_text="provider openai api-key sk-openai model gpt-5.5",
            ) or ("", [])

        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert events == []
    assert "connect_persisted=true" in text
    assert payload["model"] == "gpt-5.5"
    assert payload["models"]["gpt_5_5"]["provider"] == "openai"
    assert payload["models"]["gpt_5_5"]["model_id"] == "gpt-5.5"
