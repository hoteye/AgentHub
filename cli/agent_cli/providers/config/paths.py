from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cli.agent_cli.runtime_paths import agent_cli_home, is_frozen_runtime

AGENTHUB_PROVIDER_HOME_ENV = "AGENTHUB_PROVIDER_HOME"
PROJECT_PROVIDER_HOME_DIRNAME = ".config"


@dataclass(frozen=True)
class ProjectProviderLayout:
    home_dir: Path
    providers_dir: Path
    config_toml: Path
    auth_json: Path
    openai_provider_toml: Path
    openai_auth_json: Path
    anthropic_snapshot_settings_json: Path
    anthropic_snapshot_config_json: Path
    anthropic_snapshot_state_json: Path
    claude_home_dir: Path
    claude_settings_path: Path
    claude_config_path: Path
    claude_state_path: Path


def default_cli_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _build_project_provider_layout(
    base: Path, *, config_in_providers_dir: bool
) -> ProjectProviderLayout:
    providers_dir = base / "providers"
    config_dir = providers_dir if config_in_providers_dir else base
    return ProjectProviderLayout(
        home_dir=base,
        providers_dir=providers_dir,
        config_toml=config_dir / "config.toml",
        auth_json=config_dir / "auth.json",
        openai_provider_toml=providers_dir / "openai" / "provider.toml",
        openai_auth_json=providers_dir / "openai" / "auth.json",
        anthropic_snapshot_settings_json=providers_dir / "anthropic" / "settings.json",
        anthropic_snapshot_config_json=providers_dir / "anthropic" / "config.json",
        anthropic_snapshot_state_json=providers_dir / "anthropic" / "state.json",
        claude_home_dir=base,
        claude_settings_path=base / ".claude" / "settings.json",
        claude_config_path=base / ".claude" / "config.json",
        claude_state_path=base / ".claude.json",
    )


def project_provider_layout(*, cli_root: Path | None = None) -> ProjectProviderLayout:
    if is_frozen_runtime() and not str(os.environ.get(AGENTHUB_PROVIDER_HOME_ENV) or "").strip():
        return _build_project_provider_layout(agent_cli_home(), config_in_providers_dir=False)
    base = Path(
        os.environ.get(AGENTHUB_PROVIDER_HOME_ENV)
        or ((cli_root or default_cli_root()) / PROJECT_PROVIDER_HOME_DIRNAME)
    )
    return _build_project_provider_layout(base, config_in_providers_dir=False)
