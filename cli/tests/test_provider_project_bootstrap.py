from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cli.agent_cli.provider import load_provider_config, resolve_provider_paths
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV


def _patch_project_provider_layout(root: Path):
    project_home = root / "cli" / ".config"
    return patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=True)


def test_load_provider_config_bootstraps_legacy_compat_home_into_explicit_runtime_home() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy_compat = root / "home" / ".agent_cli_legacy"
        legacy_compat.mkdir(parents=True, exist_ok=True)
        (legacy_compat / "config.toml").write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.4"\n'
            "[model_providers.openai]\n"
            'base_url = "https://relay.example/v1"\n',
            encoding="utf-8",
        )
        (legacy_compat / "auth.json").write_text(
            '{"OPENAI_API_KEY":"sk-bootstrap"}', encoding="utf-8"
        )

        missing = root / "missing"
        with _patch_project_provider_layout(root):
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch(
                        "cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML",
                        legacy_compat / "config.toml",
                    ):
                        with patch(
                            "cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON",
                            legacy_compat / "auth.json",
                        ):
                            with patch(
                                "cli.agent_cli.provider.CLAUDE_SETTINGS_JSON",
                                missing / "settings.json",
                            ):
                                with patch(
                                    "cli.agent_cli.provider.CLAUDE_CONFIG_JSON",
                                    missing / "config.json",
                                ):
                                    with patch(
                                        "cli.agent_cli.provider.CLAUDE_STATE_JSON",
                                        missing / "state.json",
                                    ):
                                        with patch(
                                            "cli.agent_cli.provider._find_project_provider_file",
                                            return_value=None,
                                        ):
                                            with patch.dict(
                                                os.environ,
                                                {
                                                    AGENTHUB_PROVIDER_HOME_ENV: str(
                                                        root / "cli" / ".config"
                                                    )
                                                },
                                                clear=True,
                                            ):
                                                config = load_provider_config()
                                                resolved = resolve_provider_paths()

        assert config is not None
        assert config.source == "agent_cli_home"
        assert config.model == "gpt-5.4"
        assert config.api_key == "sk-bootstrap"
        assert config.config_path == str(root / "cli" / ".config" / "config.toml")
        assert config.auth_path == str(legacy_compat / "auth.json")
        assert resolved.used_project_local is False
        assert (root / "cli" / ".config" / "config.toml").exists()
        assert not (root / "cli" / ".config" / "auth.json").exists()
        assert (root / "cli" / ".config" / "providers" / "openai" / "provider.toml").exists()
        assert not (root / "cli" / ".config" / "providers" / "openai" / "auth.json").exists()


def test_load_provider_config_routes_to_explicit_runtime_claude_snapshot_after_bootstrap() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy_claude_home = root / "home"
        claude_dir = legacy_claude_home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://claude.example/api"}}),
            encoding="utf-8",
        )
        (claude_dir / "config.json").write_text(
            json.dumps({"primaryApiKey": "sk-claude-bootstrap"}),
            encoding="utf-8",
        )
        (legacy_claude_home / ".claude.json").write_text(
            json.dumps({"hasCompletedOnboarding": True}),
            encoding="utf-8",
        )

        missing = root / "missing"
        with _patch_project_provider_layout(root):
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch(
                        "cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"
                    ):
                        with patch(
                            "cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"
                        ):
                            with patch(
                                "cli.agent_cli.provider.CLAUDE_SETTINGS_JSON",
                                claude_dir / "settings.json",
                            ):
                                with patch(
                                    "cli.agent_cli.provider.CLAUDE_CONFIG_JSON",
                                    claude_dir / "config.json",
                                ):
                                    with patch(
                                        "cli.agent_cli.provider.CLAUDE_STATE_JSON",
                                        legacy_claude_home / ".claude.json",
                                    ):
                                        with patch(
                                            "cli.agent_cli.provider._find_project_provider_file",
                                            return_value=None,
                                        ):
                                            with patch.dict(
                                                os.environ,
                                                {
                                                    AGENTHUB_PROVIDER_HOME_ENV: str(
                                                        root / "cli" / ".config"
                                                    )
                                                },
                                                clear=True,
                                            ):
                                                config = load_provider_config(
                                                    env_overrides={"AGENT_CLI_PROVIDER": "claude"}
                                                )

        assert config is not None
        assert config.provider_name == "anthropic"
        assert config.api_key == "sk-claude-bootstrap"
        assert config.base_url == "https://claude.example/api"
        assert config.config_path == str(root / "cli" / ".config" / ".claude" / "settings.json")
        assert config.auth_path == str(root / "cli" / ".config" / ".claude" / "config.json")
        assert (root / "cli" / ".config" / ".claude" / "settings.json").exists()
        assert (root / "cli" / ".config" / ".claude" / "config.json").exists()
        assert (root / "cli" / ".config" / ".claude.json").exists()


def test_load_provider_config_ignores_untrusted_workspace_layers_against_explicit_runtime_home() -> (
    None
):
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace" / "app"
        local_config_home = workspace.parent / ".config"
        project_config_home = root / "cli" / ".config"
        workspace.mkdir(parents=True, exist_ok=True)
        local_config_home.mkdir(parents=True, exist_ok=True)
        project_config_home.mkdir(parents=True, exist_ok=True)

        (local_config_home / "config.toml").write_text(
            'model_provider = "openai"\n'
            'model = "gpt-untrusted"\n'
            "[model_providers.openai]\n"
            'base_url = "https://untrusted.example/v1"\n',
            encoding="utf-8",
        )
        (local_config_home / "auth.json").write_text(
            '{"OPENAI_API_KEY":"sk-untrusted"}', encoding="utf-8"
        )
        (project_config_home / "config.toml").write_text(
            'model_provider = "openai"\n'
            'model = "gpt-home"\n'
            "[model_providers.openai]\n"
            'base_url = "https://home.example/v1"\n'
            f'\n[projects."{str(workspace.parent.resolve()).replace(chr(92), "/")}"]\n'
            'trust_level = "untrusted"\n',
            encoding="utf-8",
        )
        (project_config_home / "auth.json").write_text(
            '{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8"
        )

        missing = root / "missing"
        with _patch_project_provider_layout(root):
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch(
                        "cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"
                    ):
                        with patch(
                            "cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"
                        ):
                            with patch(
                                "cli.agent_cli.provider.CLAUDE_SETTINGS_JSON",
                                missing / "settings.json",
                            ):
                                with patch(
                                    "cli.agent_cli.provider.CLAUDE_CONFIG_JSON",
                                    missing / "config.json",
                                ):
                                    with patch(
                                        "cli.agent_cli.provider.CLAUDE_STATE_JSON",
                                        missing / "state.json",
                                    ):
                                        with patch.dict(
                                            os.environ,
                                            {
                                                AGENTHUB_PROVIDER_HOME_ENV: str(
                                                    root / "cli" / ".config"
                                                )
                                            },
                                            clear=True,
                                        ):
                                            config = load_provider_config(cwd=workspace)

        assert config is not None
        assert config.source == "agent_cli_home"
        assert config.model == "gpt-home"
        assert config.base_url == "https://home.example/v1"
        assert config.api_key == "sk-home"
        assert config.config_path == str(project_config_home / "config.toml")
        assert config.auth_path == str(project_config_home / "auth.json")


def test_load_provider_config_does_not_merge_workspace_layers_into_explicit_runtime_home() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "apps" / "api"
        workspace.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text("gitdir: here\n", encoding="utf-8")
        (root / ".config").mkdir(parents=True, exist_ok=True)
        (workspace / ".config").mkdir(parents=True, exist_ok=True)
        project_config_home = root / "cli" / ".config"
        project_config_home.mkdir(parents=True, exist_ok=True)

        (project_config_home / "config.toml").write_text(
            'model_provider = "openai"\n'
            "[model_providers.openai]\n"
            'base_url = "https://home.example/v1"\n'
            'default_model = "gpt-home"\n',
            encoding="utf-8",
        )
        (project_config_home / "auth.json").write_text(
            '{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8"
        )
        (root / ".config" / "config.toml").write_text(
            "[model_providers.openai]\n" 'base_url = "https://root.example/v1"\n',
            encoding="utf-8",
        )
        (workspace / ".config" / "config.toml").write_text(
            'model = "gpt-child"\n' "[model_providers.openai]\n" 'default_model = "gpt-child"\n',
            encoding="utf-8",
        )

        missing = root / "missing"
        with _patch_project_provider_layout(root):
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch(
                        "cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"
                    ):
                        with patch(
                            "cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"
                        ):
                            with patch(
                                "cli.agent_cli.provider.CLAUDE_SETTINGS_JSON",
                                missing / "settings.json",
                            ):
                                with patch(
                                    "cli.agent_cli.provider.CLAUDE_CONFIG_JSON",
                                    missing / "config.json",
                                ):
                                    with patch(
                                        "cli.agent_cli.provider.CLAUDE_STATE_JSON",
                                        missing / "state.json",
                                    ):
                                        with patch.dict(
                                            os.environ,
                                            {
                                                AGENTHUB_PROVIDER_HOME_ENV: str(
                                                    root / "cli" / ".config"
                                                )
                                            },
                                            clear=True,
                                        ):
                                            config = load_provider_config(cwd=workspace)

        assert config is not None
        assert config.source == "agent_cli_home"
        assert config.model == "gpt-home"
        assert config.base_url == "https://home.example/v1"
        assert config.api_key == "sk-home"
        assert config.config_path == str(project_config_home / "config.toml")
        assert config.auth_path == str(project_config_home / "auth.json")
