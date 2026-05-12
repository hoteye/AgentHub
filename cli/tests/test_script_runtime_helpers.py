from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.agent_cli import provider as provider_module
from cli.agent_cli import provider_catalog_runtime as provider_catalog_runtime_lib
from cli.scripts import script_runtime_helpers as module


def test_ensure_script_import_paths_adds_cli_and_repo_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sys_path = list(sys.path)
    script_file = Path("/tmp/demo/cli/scripts/example.py")
    cli_root = str(script_file.resolve().parents[1])
    repo_root = str(script_file.resolve().parents[2])
    filtered = [item for item in original_sys_path if item not in {cli_root, repo_root}]
    monkeypatch.setattr(sys, "path", filtered)

    paths = module.ensure_script_import_paths(script_file)

    assert paths.cli_root == Path(cli_root)
    assert paths.repo_root == Path(repo_root)
    assert cli_root in sys.path
    assert repo_root in sys.path


def test_ensure_script_import_paths_handles_nested_script(monkeypatch: pytest.MonkeyPatch) -> None:
    original_sys_path = list(sys.path)
    script_file = Path("/tmp/demo/cli/scripts/experiments/weather/replay.py")
    cli_root = str(Path("/tmp/demo/cli"))
    repo_root = str(Path("/tmp/demo"))
    filtered = [item for item in original_sys_path if item not in {cli_root, repo_root}]
    monkeypatch.setattr(sys, "path", filtered)

    paths = module.ensure_script_import_paths(script_file)

    assert paths.cli_root == Path(cli_root)
    assert paths.repo_root == Path(repo_root)
    assert cli_root in sys.path
    assert repo_root in sys.path


def test_resolve_model_and_reasoning_settings_uses_catalog_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module, "load_provider_catalog", lambda cwd: {"cwd": str(cwd)})
    monkeypatch.setattr(
        provider_catalog_runtime_lib,
        "model_catalog_reasoning_profile",
        lambda **kwargs: {
            "model_id": "gpt-5.4",
            "supported_reasoning_efforts": ("low", "medium", "high", "xhigh"),
            "default_reasoning_effort": "xhigh",
        },
    )

    resolved_model, resolved_effort = module.resolve_model_and_reasoning_settings(
        provider="openai",
        model="gpt_54",
        reasoning_effort="",
        catalog_cwd=Path("/tmp/catalog"),
        interaction_profile="codex_openai",
    )

    assert resolved_model == "gpt-5.4"
    assert resolved_effort == "xhigh"


def test_resolve_model_and_reasoning_settings_rejects_unsupported_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module, "load_provider_catalog", lambda cwd: {"cwd": str(cwd)})
    monkeypatch.setattr(
        provider_catalog_runtime_lib,
        "model_catalog_reasoning_profile",
        lambda **kwargs: {
            "model_id": "claude-opus-4-6",
            "supported_reasoning_efforts": ("low", "medium", "high"),
            "default_reasoning_effort": "",
        },
    )

    with pytest.raises(
        SystemExit, match="unsupported reasoning_effort `xhigh` for model `claude-opus-4-6`"
    ):
        module.resolve_model_and_reasoning_settings(
            provider="anthropic",
            model="claude_opus_46",
            reasoning_effort="xhigh",
            catalog_cwd=Path("/tmp/catalog"),
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )


def test_load_script_provider_management_snapshot_delegates_to_provider_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    monkeypatch.setattr(
        provider_module,
        "load_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )

    snapshot = module.load_script_provider_management_snapshot(cwd=Path("/tmp/catalog"))

    assert snapshot is sentinel


def test_resolve_script_provider_source_paths_uses_unified_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = type(
        "Snapshot",
        (),
        {
            "resolution": type(
                "Resolution",
                (),
                {
                    "config_path": Path("/tmp/provider/config.toml"),
                    "auth_path": Path("/tmp/provider/auth.json"),
                },
            )(),
        },
    )()
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )

    config_path, auth_path = module.resolve_script_provider_source_paths(cwd=Path("/tmp/catalog"))

    assert config_path == Path("/tmp/provider/config.toml")
    assert auth_path == Path("/tmp/provider/auth.json")


def test_resolve_codex_source_paths_prefers_code_home_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")

    paths = module.resolve_codex_source_paths()

    assert paths.home == Path("/tmp/codex-home")
    assert paths.config_path == Path("/tmp/codex-home/config.toml")
    assert paths.auth_path == Path("/tmp/codex-home/auth.json")
    assert paths.skills_dir == Path("/tmp/codex-home/skills")


def test_resolve_codex_source_paths_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_HOME", "/tmp/ignored-codex-home")

    paths = module.resolve_codex_source_paths(home_override="/tmp/explicit-codex-home")

    assert paths.home == Path("/tmp/explicit-codex-home")
    assert paths.config_path == Path("/tmp/explicit-codex-home/config.toml")


def test_resolve_script_provider_home_dir_uses_snapshot_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = type(
        "Snapshot",
        (),
        {
            "resolution": type(
                "Resolution",
                (),
                {
                    "config_path": Path("/tmp/provider-home/config.toml"),
                },
            )(),
        },
    )()
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )

    provider_home = module.resolve_script_provider_home_dir(cwd=Path("/tmp/catalog"))

    assert provider_home == Path("/tmp/provider-home")


def test_resolve_script_provider_run_settings_uses_selected_config_paths_and_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    resolution_config = tmp_path / "resolution" / "config.toml"
    resolution_auth = tmp_path / "resolution" / "auth.json"
    selected_config = tmp_path / "selected" / "config.toml"
    selected_auth = tmp_path / "selected" / "auth.json"
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=resolution_config,
            auth_path=resolution_auth,
        ),
        selected_config=SimpleNamespace(
            provider_name="openai",
            model_key="gpt_55",
            model="gpt-5.5",
            reasoning_effort="xhigh",
            base_url="https://gaccode.com/codex/v1",
            config_path=str(selected_config),
            auth_path=str(selected_auth),
            api_key="sk-selected",
            source="project_local",
        ),
    )
    received = {}

    def _fake_snapshot(**kwargs):
        received.update(kwargs)
        return snapshot

    monkeypatch.setattr(module, "load_script_provider_management_snapshot", _fake_snapshot)
    monkeypatch.setattr(
        module, "resolve_model_and_reasoning_settings", lambda **_kwargs: ("gpt-5.5", "xhigh")
    )

    settings = module.resolve_script_provider_run_settings(
        cwd=tmp_path / "cli",
        catalog_cwd=tmp_path / "catalog",
        interaction_profile="codex_openai",
    )

    assert received["cwd"] == tmp_path / "cli"
    assert settings.provider_name == "openai"
    assert settings.model_key == "gpt_55"
    assert settings.model == "gpt-5.5"
    assert settings.reasoning_effort == "xhigh"
    assert settings.base_url == "https://gaccode.com/codex/v1"
    assert settings.config_path == selected_config.resolve()
    assert settings.auth_path == selected_auth.resolve()
    assert settings.api_key == "sk-selected"
    assert settings.source == "project_local"


def test_resolve_script_provider_run_settings_passes_overrides_as_selection_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=tmp_path / "config.toml",
            auth_path=tmp_path / "auth.json",
        ),
        selected_config=SimpleNamespace(
            provider_name="openai",
            model_key="gpt_55",
            model="gpt-5.5",
            reasoning_effort="high",
            base_url="https://override.example/v1",
            config_path="",
            auth_path="",
            api_key="sk-selected",
            source="env",
        ),
    )
    received = {}

    def _fake_snapshot(**kwargs):
        received.update(kwargs)
        return snapshot

    def _fake_model_resolver(**kwargs):
        assert kwargs["provider"] == "openai"
        assert kwargs["model"] == "gpt_55"
        assert kwargs["reasoning_effort"] == "high"
        assert kwargs["catalog_cwd"] == tmp_path / "catalog"
        return "gpt-5.5", "high"

    monkeypatch.setattr(module, "load_script_provider_management_snapshot", _fake_snapshot)
    monkeypatch.setattr(module, "resolve_model_and_reasoning_settings", _fake_model_resolver)

    settings = module.resolve_script_provider_run_settings(
        cwd=tmp_path / "cli",
        provider="openai",
        model="gpt_55",
        reasoning_effort="high",
        base_url="https://override.example/v1",
        env_overrides={"OPENAI_API_KEY": "sk-env"},
        catalog_cwd=tmp_path / "catalog",
    )

    assert received["env_overrides"] == {
        "OPENAI_API_KEY": "sk-env",
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt_55",
        "AGENT_CLI_REASONING_EFFORT": "high",
        "AGENT_CLI_BASE_URL": "https://override.example/v1",
    }
    assert settings.base_url == "https://override.example/v1"
    assert settings.config_path == (tmp_path / "config.toml").resolve()
    assert settings.auth_path == (tmp_path / "auth.json").resolve()


def test_normalize_optional_provider_home_override_returns_empty_for_unset() -> None:
    assert module.normalize_optional_provider_home_override("") == ""
    assert module.normalize_optional_provider_home_override(None) == ""


def test_normalize_optional_provider_home_override_resolves_path(tmp_path: Path) -> None:
    provider_home = module.normalize_optional_provider_home_override(tmp_path / "provider-home")

    assert provider_home == str((tmp_path / "provider-home").resolve())


def test_resolve_effective_script_provider_home_dir_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "resolve_script_provider_home_dir",
        lambda **kwargs: Path("/tmp/runtime-provider-home"),
    )

    provider_home = module.resolve_effective_script_provider_home_dir(
        cwd=Path("/tmp/catalog"),
        provider_home="/tmp/explicit-provider-home",
    )

    assert provider_home == Path("/tmp/explicit-provider-home")


def test_normalize_script_validation_command_uses_current_python_for_pytest() -> None:
    command = module.normalize_script_validation_command(("pytest", "-q", "tests/test_demo.py"))

    assert command == [sys.executable, "-m", "pytest", "-q", "tests/test_demo.py"]


def test_normalize_script_validation_command_keeps_non_pytest_command() -> None:
    command = module.normalize_script_validation_command(("python3", "task_stats.py"))

    assert command == ["python3", "task_stats.py"]


def test_apply_provider_home_override_env_omits_provider_home_and_strict_isolation_when_unset() -> (
    None
):
    env = {
        "AGENTHUB_PROVIDER_HOME": "/tmp/stale-provider-home",
        "AGENTHUB_PROVIDER_STRICT_ISOLATION": "true",
    }

    result = module.apply_provider_home_override_env(env, provider_home="")

    assert result is env
    assert "AGENTHUB_PROVIDER_HOME" not in env
    assert "AGENTHUB_PROVIDER_STRICT_ISOLATION" not in env


def test_apply_provider_home_override_env_enables_strict_isolation_for_explicit_override(
    tmp_path: Path,
) -> None:
    env = {}

    module.apply_provider_home_override_env(env, provider_home=tmp_path / "provider-home")

    assert env["AGENTHUB_PROVIDER_HOME"] == str((tmp_path / "provider-home").resolve())
    assert env["AGENTHUB_PROVIDER_STRICT_ISOLATION"] == "true"


def test_materialize_script_provider_fixture_keeps_user_home_source_as_agent_cli_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_home = tmp_path / "source-home"
    source_home.mkdir(parents=True)
    (source_home / "config.toml").write_text('model_provider = "anthropic"\n', encoding="utf-8")
    (source_home / "auth.json").write_text('{"ANTHROPIC_API_KEY":"sk-test"}\n', encoding="utf-8")
    sentinel = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=source_home / "config.toml",
            auth_path=source_home / "auth.json",
            used_project_local=False,
        ),
        selected_config=None,
    )
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )
    monkeypatch.delenv("AGENTHUB_PROVIDER_HOME", raising=False)

    fixture = module.materialize_script_provider_fixture(
        cwd=Path("/tmp/catalog"),
        target_root=tmp_path / "materialized-home",
    )

    assert fixture.source_scope == "user_home"
    assert fixture.provider_home is None
    assert fixture.agent_cli_home == (tmp_path / "materialized-home").resolve()
    assert fixture.config_path.read_text(encoding="utf-8") == 'model_provider = "anthropic"\n'
    assert fixture.auth_path.read_text(encoding="utf-8") == '{"ANTHROPIC_API_KEY":"sk-test"}\n'

    env = {
        "AGENT_CLI_HOME": "/tmp/stale-agent-cli-home",
        "AGENTHUB_PROVIDER_HOME": "/tmp/stale-provider-home",
        "AGENTHUB_PROVIDER_STRICT_ISOLATION": "true",
    }
    module.apply_script_provider_materialization_env(env, fixture=fixture)
    assert env["AGENT_CLI_HOME"] == str(fixture.agent_cli_home)
    assert "AGENTHUB_PROVIDER_HOME" not in env
    assert "AGENTHUB_PROVIDER_STRICT_ISOLATION" not in env


def test_materialize_script_provider_fixture_user_home_applies_selection_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_home = tmp_path / "source-home"
    source_home.mkdir(parents=True)
    (source_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "anthropic"',
                'model = "claude-sonnet-4-6"',
                "",
                "[model_providers.openai]",
                'base_url = "https://api.openai.com/v1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (source_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-openai"}\n', encoding="utf-8")
    sentinel = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=source_home / "config.toml",
            auth_path=source_home / "auth.json",
            used_project_local=False,
        ),
        selected_config=SimpleNamespace(
            provider_name="anthropic",
            model_key="claude-sonnet-4-6",
            model="claude-sonnet-4-6",
            reasoning_effort="high",
        ),
    )
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )

    fixture = module.materialize_script_provider_fixture(
        cwd=Path("/tmp/catalog"),
        target_root=tmp_path / "materialized-home",
        selection_override=module.ScriptProviderSelectionOverride(
            provider_name="openai",
            model="gpt-5.4",
            reasoning_effort="xhigh",
        ),
    )

    config_text = fixture.config_path.read_text(encoding="utf-8")
    assert 'model_provider = "openai"' in config_text
    assert 'model = "gpt-5.4"' in config_text
    assert 'model_reasoning_effort = "xhigh"' in config_text
    assert "[model_providers.openai]" in config_text


def test_materialize_script_provider_fixture_separates_runtime_home_from_user_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_home = tmp_path / "runtime-source"
    source_home.mkdir(parents=True)
    (source_home / ".claude").mkdir(parents=True)
    (source_home / ".claude" / "settings.json").write_text(
        '{"env":{"ANTHROPIC_API_KEY":"sk-claude"}}\n',
        encoding="utf-8",
    )
    (source_home / ".claude" / "config.json").write_text(
        '{"primaryApiKey":"sk-claude"}\n',
        encoding="utf-8",
    )
    (source_home / ".claude.json").write_text(
        '{"hasCompletedOnboarding":true}\n',
        encoding="utf-8",
    )
    (source_home / "config.toml").write_text(
        "\n".join(
            [
                "[model_providers.openai]",
                'base_url = "https://api.openai.com/v1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (source_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-openai"}\n', encoding="utf-8")
    sentinel = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=source_home / "config.toml",
            auth_path=source_home / "auth.json",
            used_project_local=True,
        ),
        auth_data={
            "OPENAI_API_KEY": "sk-openai-merged",
            "ANTHROPIC_API_KEY": "sk-anthropic-merged",
        },
        selected_config=SimpleNamespace(
            provider_name="openai",
            model_key="gpt_54",
            model="gpt-5.4",
            reasoning_effort="high",
            api_key="sk-selected",
            raw_provider={"api_key_env": "SELECTED_API_KEY"},
        ),
    )
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )
    monkeypatch.delenv("AGENTHUB_PROVIDER_HOME", raising=False)

    fixture = module.materialize_script_provider_fixture(
        cwd=Path("/tmp/catalog"),
        target_root=tmp_path / "materialized-runtime",
    )

    assert fixture.source_scope == "runtime_home"
    assert fixture.provider_home == (tmp_path / "materialized-runtime" / "provider_home").resolve()
    assert (
        fixture.agent_cli_home == (tmp_path / "materialized-runtime" / "agent_cli_home").resolve()
    )
    assert fixture.config_path.read_text(encoding="utf-8") == (
        '[model_providers.openai]\nbase_url = "https://api.openai.com/v1"\n'
    )
    auth_payload = json.loads(fixture.auth_path.read_text(encoding="utf-8"))
    assert auth_payload["OPENAI_API_KEY"] == "sk-openai-merged"
    assert auth_payload["ANTHROPIC_API_KEY"] == "sk-anthropic-merged"
    assert auth_payload["SELECTED_API_KEY"] == "sk-selected"
    assert (fixture.provider_home / ".claude" / "settings.json").read_text(
        encoding="utf-8"
    ) == '{"env":{"ANTHROPIC_API_KEY":"sk-claude"}}\n'
    assert (fixture.provider_home / ".claude" / "config.json").read_text(
        encoding="utf-8"
    ) == '{"primaryApiKey":"sk-claude"}\n'
    assert (fixture.provider_home / ".claude.json").read_text(
        encoding="utf-8"
    ) == '{"hasCompletedOnboarding":true}\n'
    assert (fixture.agent_cli_home / "config.toml").read_text(encoding="utf-8") == (
        'model_provider = "openai"\n' 'model = "gpt_54"\n' 'model_reasoning_effort = "high"\n'
    )

    env = {}
    module.apply_script_provider_materialization_env(env, fixture=fixture)
    assert env["AGENT_CLI_HOME"] == str(fixture.agent_cli_home)
    assert env["AGENTHUB_PROVIDER_HOME"] == str(fixture.provider_home)
    assert env["AGENTHUB_PROVIDER_STRICT_ISOLATION"] == "true"


def test_materialize_script_provider_fixture_runtime_home_applies_selection_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_home = tmp_path / "runtime-source"
    source_home.mkdir(parents=True)
    (source_home / "config.toml").write_text(
        '[model_providers.openai]\nbase_url = "https://api.openai.com/v1"\n', encoding="utf-8"
    )
    (source_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-openai"}\n', encoding="utf-8")
    sentinel = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=source_home / "config.toml",
            auth_path=source_home / "auth.json",
            used_project_local=True,
        ),
        selected_config=SimpleNamespace(
            provider_name="anthropic",
            model_key="claude-sonnet-4-6",
            model="claude-sonnet-4-6",
            reasoning_effort="high",
        ),
    )
    monkeypatch.setattr(
        module,
        "load_script_provider_management_snapshot",
        lambda **kwargs: sentinel,
    )

    fixture = module.materialize_script_provider_fixture(
        cwd=Path("/tmp/catalog"),
        target_root=tmp_path / "materialized-runtime",
        selection_override=module.ScriptProviderSelectionOverride(
            provider_name="openai",
            model="gpt-5.4",
            reasoning_effort="xhigh",
        ),
    )

    assert (fixture.agent_cli_home / "config.toml").read_text(encoding="utf-8") == (
        'model_provider = "openai"\n' 'model = "gpt-5.4"\n' 'model_reasoning_effort = "xhigh"\n'
    )
