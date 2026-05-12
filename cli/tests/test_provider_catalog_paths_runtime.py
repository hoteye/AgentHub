from pathlib import Path

from cli.agent_cli.provider_catalog_paths_runtime import (
    _apply_user_model_selection,
    home_provider_paths,
    load_provider_inputs,
)
from cli.agent_cli.providers.config.catalog import ProviderPathResolution


def test_apply_user_model_selection_ignores_stale_selector_outside_catalog() -> None:
    toml_data = {
        "model_provider": "deepseek",
        "model": "deepseek-reasoner",
        "model_providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
            }
        },
    }

    result = _apply_user_model_selection(
        toml_data=toml_data,
        user_model_selection={
            "model_provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "model_reasoning_effort": "high",
        },
    )

    assert result == toml_data


def test_apply_user_model_selection_keeps_project_reasoning_when_explicit() -> None:
    toml_data = {
        "model_provider": "openai",
        "model": "gpt_project",
        "model_reasoning_effort": "xhigh",
        "model_providers": {
            "openai": {
                "base_url": "https://project.example/v1",
            }
        },
        "models": {
            "gpt_project": {
                "provider": "openai",
                "model_id": "gpt-5.4",
            }
        },
    }

    result = _apply_user_model_selection(
        toml_data=toml_data,
        user_model_selection={
            "model_provider": "openai",
            "model": "gpt_project",
            "model_reasoning_effort": "high",
        },
    )

    assert result["model_provider"] == "openai"
    assert result["model"] == "gpt_project"
    assert result["model_reasoning_effort"] == "xhigh"


def test_apply_user_model_selection_uses_user_reasoning_when_target_changes() -> None:
    toml_data = {
        "model_provider": "openai",
        "model": "gpt_project",
        "model_reasoning_effort": "xhigh",
        "model_providers": {
            "openai": {"base_url": "https://openai.example/v1"},
            "anthropic": {"base_url": "https://anthropic.example/v1"},
        },
        "models": {
            "gpt_project": {"provider": "openai", "model_id": "gpt-5.5"},
            "claude_sonnet_46": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
        },
    }

    result = _apply_user_model_selection(
        toml_data=toml_data,
        user_model_selection={
            "model_provider": "anthropic",
            "model": "claude_sonnet_46",
            "model_reasoning_effort": "high",
        },
    )

    assert result["model_provider"] == "anthropic"
    assert result["model"] == "claude_sonnet_46"
    assert result["model_reasoning_effort"] == "high"


def test_load_provider_inputs_keeps_user_selection_after_project_overlay() -> None:
    home_config = Path("/tmp/home/config.toml")
    home_auth = Path("/tmp/home/auth.json")
    project_config = Path("/tmp/project/.config/config.toml")
    project_auth = Path("/tmp/project/.config/auth.json")
    toml_payloads = {
        home_config: {
            "model_provider": "openai",
            "model": "gpt_project",
            "model_providers": {
                "openai": {"base_url": "https://openai.example/v1"},
                "anthropic": {"base_url": "https://anthropic.example/v1"},
            },
            "models": {
                "gpt_project": {"provider": "openai", "model_id": "gpt-5.5"},
                "claude_sonnet_46": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
            },
        },
        project_config: {
            "model_provider": "openai",
            "model": "gpt_project",
            "model_reasoning_effort": "xhigh",
        },
    }

    resolution, toml_data, _ = load_provider_inputs(
        cwd=Path("/tmp/project"),
        resolve_provider_paths_fn=lambda **_kwargs: ProviderPathResolution(
            config_path=project_config,
            auth_path=project_auth,
            config_exists=True,
            auth_exists=True,
            used_project_local=True,
        ),
        home_provider_paths_fn=lambda: (home_config, home_auth, True),
        discover_provider_project_local_paths_fn=lambda filename, **_kwargs: (
            [home_config, project_config]
            if filename == "config.toml"
            else [home_auth, project_auth]
        ),
        read_toml_fn=lambda path: dict(toml_payloads.get(path, {})),
        read_json_fn=lambda _path: {},
        read_user_model_selection_toml_fn=lambda: {
            "model_provider": "anthropic",
            "model": "claude_sonnet_46",
            "model_reasoning_effort": "high",
        },
    )

    assert resolution.config_path == project_config
    assert toml_data["model_provider"] == "anthropic"
    assert toml_data["model"] == "claude_sonnet_46"
    assert toml_data["model_reasoning_effort"] == "high"


def test_load_provider_inputs_merges_private_auth_after_project_auth(tmp_path: Path) -> None:
    home_config = tmp_path / "home" / "config.toml"
    home_auth = tmp_path / "home" / "auth.json"
    project_config = tmp_path / "project" / ".config" / "config.toml"
    project_auth = tmp_path / "project" / ".config" / "auth.json"
    legacy_auth = tmp_path / "legacy" / ".agent_cli_legacy" / "auth.json"
    private_auth = tmp_path / "user" / ".agent_cli" / "auth.json"
    for path in (project_config, project_auth, legacy_auth, private_auth):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    toml_payloads = {
        project_config: {
            "model_provider": "openai",
            "model": "gpt_project",
            "model_providers": {
                "openai": {"base_url": "https://openai.example/v1"},
            },
            "models": {
                "gpt_project": {"provider": "openai", "model_id": "gpt-5.5"},
            },
        },
    }
    auth_payloads = {
        project_auth: {"OPENAI_API_KEY": "sk-project", "PROJECT_ONLY": "kept"},
        legacy_auth: {"OPENAI_API_KEY": "sk-legacy", "LEGACY_ONLY": "kept"},
        private_auth: {"OPENAI_API_KEY": "sk-user"},
    }

    resolution, _toml_data, auth_data = load_provider_inputs(
        cwd=Path("/tmp/project"),
        resolve_provider_paths_fn=lambda **_kwargs: ProviderPathResolution(
            config_path=project_config,
            auth_path=project_auth,
            config_exists=True,
            auth_exists=True,
            used_project_local=True,
        ),
        home_provider_paths_fn=lambda: (home_config, home_auth, False),
        discover_provider_project_local_paths_fn=lambda filename, **_kwargs: (
            [project_config] if filename == "config.toml" else [project_auth]
        ),
        read_toml_fn=lambda path: dict(toml_payloads.get(path, {})),
        read_json_fn=lambda path: dict(auth_payloads.get(path, {})),
        read_user_model_selection_toml_fn=lambda: {},
        private_auth_paths_fn=lambda: [legacy_auth, private_auth],
    )

    assert auth_data["OPENAI_API_KEY"] == "sk-user"
    assert auth_data["PROJECT_ONLY"] == "kept"
    assert auth_data["LEGACY_ONLY"] == "kept"
    assert resolution.auth_path == private_auth


def test_load_provider_inputs_uses_private_provider_profile_for_project_selection(
    tmp_path: Path,
) -> None:
    home_config = tmp_path / "repo" / ".config" / "config.toml"
    home_auth = tmp_path / "repo" / ".config" / "auth.json"
    private_config = tmp_path / "home" / ".agent_cli" / "config.toml"
    project_config = tmp_path / "project" / ".agent_cli" / "config.toml"
    project_auth = tmp_path / "project" / ".agent_cli" / "auth.json"
    for path in (private_config, project_config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    toml_payloads = {
        private_config: {
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "auth_mode": "api_key",
                    "api_key_env": "OPENAI_API_KEY",
                },
            },
            "provider_profiles": {
                "openai_relay": {
                    "provider": "openai",
                    "model": "gpt-5.5",
                    "base_url": "https://relay.example/v1",
                    "auth_mode": "api_key",
                    "api_key_env": "OPENAI_API_KEY",
                },
            },
        },
        project_config: {
            "model": "gpt-5.5",
            "provider_profile": "openai_relay",
        },
    }

    resolution, toml_data, _auth_data = load_provider_inputs(
        cwd=tmp_path / "project",
        resolve_provider_paths_fn=lambda **_kwargs: ProviderPathResolution(
            config_path=project_config,
            auth_path=project_auth,
            config_exists=True,
            auth_exists=False,
            used_project_local=True,
        ),
        home_provider_paths_fn=lambda: (home_config, home_auth, False),
        discover_provider_project_local_paths_fn=lambda filename, **_kwargs: (
            [project_config] if filename == "config.toml" else []
        ),
        read_toml_fn=lambda path: dict(toml_payloads.get(path, {})),
        read_json_fn=lambda _path: {},
        read_user_model_selection_toml_fn=lambda: {},
        private_config_paths_fn=lambda: [private_config],
    )

    assert resolution.config_path == project_config
    assert toml_data["provider_profile_active"] == "openai_relay"
    assert toml_data["provider_profile_source"] == "project.provider_profile"
    assert toml_data["model_provider"] == "openai"
    assert toml_data["model"] == "gpt-5.5"
    assert toml_data["model_providers"]["openai"]["base_url"] == "https://relay.example/v1"
    assert toml_data["model_providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"


def test_load_provider_inputs_merges_private_auth_in_strict_runtime_home(
    tmp_path: Path,
) -> None:
    runtime_config = tmp_path / "runtime-home" / "config.toml"
    runtime_auth = tmp_path / "runtime-home" / "auth.json"
    private_auth = tmp_path / "home" / ".agent_cli" / "auth.json"
    runtime_config.parent.mkdir(parents=True, exist_ok=True)
    private_auth.parent.mkdir(parents=True, exist_ok=True)
    runtime_config.write_text("", encoding="utf-8")
    private_auth.write_text("", encoding="utf-8")
    auth_payloads = {
        private_auth: {"OPENAI_API_KEY": "sk-user"},
    }

    resolution, _toml_data, auth_data = load_provider_inputs(
        cwd=None,
        resolve_provider_paths_fn=lambda **_kwargs: ProviderPathResolution(
            config_path=runtime_config,
            auth_path=runtime_auth,
            config_exists=True,
            auth_exists=False,
            used_project_local=False,
        ),
        home_provider_paths_fn=lambda: (runtime_config, runtime_auth, False),
        discover_provider_project_local_paths_fn=lambda _filename, **_kwargs: [],
        read_toml_fn=lambda _path: {},
        read_json_fn=lambda path: dict(auth_payloads.get(path, {})),
        read_user_model_selection_toml_fn=lambda: {},
        private_auth_paths_fn=lambda: [private_auth],
        strict_isolation=True,
    )

    assert auth_data["OPENAI_API_KEY"] == "sk-user"
    assert resolution.config_path == runtime_config
    assert resolution.auth_path == private_auth
    assert resolution.used_project_local is False


def test_home_provider_paths_treats_agent_cli_home_layout_as_user_home(tmp_path: Path) -> None:
    agent_home = tmp_path / ".agent_cli"
    config_path = agent_home / "config.toml"
    auth_path = agent_home / "auth.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('model_provider = "openai"\n', encoding="utf-8")

    home_config, home_auth, home_is_project_local = home_provider_paths(
        ensure_project_provider_bootstrap_fn=lambda: None,
        project_provider_layout_fn=lambda: type(
            "Layout",
            (),
            {
                "config_toml": config_path,
                "auth_json": auth_path,
            },
        )(),
        agent_cli_config_toml=config_path,
        agent_cli_auth_json=auth_path,
        legacy_compat_config_toml=tmp_path / ".agent_cli_legacy" / "config.toml",
        legacy_compat_auth_json=tmp_path / ".agent_cli_legacy" / "auth.json",
    )

    assert home_config == config_path
    assert home_auth == auth_path
    assert home_is_project_local is False
