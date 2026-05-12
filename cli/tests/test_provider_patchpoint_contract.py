from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cli.agent_cli import agent_provider_runtime_helpers
from cli.agent_cli.provider import load_provider_config, save_user_model_selection
from cli.agent_cli.providers.config.catalog import build_provider_catalog
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV


def test_save_user_model_selection_honors_patched_agent_cli_config_path() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patched_config = root / "patched-home" / "config.toml"
        patched_config.parent.mkdir(parents=True, exist_ok=True)

        with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", patched_config):
            returned = save_user_model_selection(provider_name="glm", model="glm_5")

        payload = tomllib.loads(patched_config.read_text(encoding="utf-8"))
        assert returned == patched_config
        assert payload["model_provider"] == "glm"
        assert payload["model"] == "glm_5"


def test_load_provider_config_reads_from_patched_paths_and_not_default_home() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patched_home = root / "patched-home"
        patched_config = patched_home / "config.toml"
        patched_auth = patched_home / "auth.json"
        patched_home.mkdir(parents=True, exist_ok=True)

        patched_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    "[model_providers.openai]",
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'default_model = "gpt_54"',
                    "[models.gpt_54]",
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        patched_auth.write_text(json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8")

        fake_home = root / "fake-home"
        default_home_config = fake_home / ".agent_cli" / "config.toml"
        default_home_auth = fake_home / ".agent_cli" / "auth.json"

        missing = root / "missing"
        with patch.dict(os.environ, {"HOME": str(fake_home), AGENTHUB_PROVIDER_HOME_ENV: str(patched_home)}, clear=False):
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", patched_config):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", patched_auth):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch("cli.agent_cli.provider._find_project_provider_file", return_value=None):
                                    config = load_provider_config(cwd=root)

        assert config is not None
        assert config.provider_name == "openai"
        assert config.model == "gpt-5.4"
        assert config.config_path == str(patched_config)
        assert config.auth_path == str(patched_auth)
        assert not default_home_config.exists()
        assert not default_home_auth.exists()


def test_configure_model_selection_falls_back_when_preferred_provider_mismatch() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model": "gpt_54",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "default_model": "gpt_54",
                },
                "glm": {
                    "base_url": "https://glm.example/v1",
                    "default_model": "glm_5",
                },
            },
            "models": {
                "gpt_54": {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                },
                "glm_5": {
                    "provider": "glm",
                    "model": "glm-5",
                    "planner_kind": "openai_chat",
                    "wire_api": "openai_chat",
                },
            },
        }
    )

    class _FakeAgent:
        def __init__(self) -> None:
            self._session_provider_env_overrides: dict[str, str] = {}
            self.reload_count = 0

        @staticmethod
        def _provider_loader_kwargs() -> dict[str, str]:
            return {}

        @staticmethod
        def _validated_reasoning_effort(effort: str) -> str:
            return effort

        def _reload_planner(self) -> None:
            self.reload_count += 1

    agent = _FakeAgent()

    def _provider_status(runtime_agent: _FakeAgent) -> dict[str, str]:
        effective_provider = str(
            runtime_agent._session_provider_env_overrides.get("AGENT_CLI_PROVIDER") or "openai"
        ).strip()
        return {
            "provider_ready": "true",
            "provider_name": effective_provider,
        }

    status = agent_provider_runtime_helpers.configure_model_selection_impl(
        agent,
        model="glm_5",
        reasoning_effort=None,
        session_model_default_tokens={"default"},
        load_provider_catalog_fn=lambda **_: catalog,
        provider_status_fn=_provider_status,
    )

    assert agent.reload_count == 1
    assert agent._session_provider_env_overrides["AGENT_CLI_PROVIDER"] == "glm"
    assert agent._session_provider_env_overrides["AGENT_CLI_MODEL"] == "glm_5"
    assert status["provider_name"] == "glm"
