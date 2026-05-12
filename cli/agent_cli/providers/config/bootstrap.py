from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectProviderBootstrapResult:
    bootstrapped: bool
    source_name: str


def _copy_file_if_present(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return True


def ensure_project_provider_bootstrap(
    *,
    project_config_toml: Path,
    project_auth_json: Path,
    project_openai_provider_toml: Path,
    project_openai_auth_json: Path,
    project_claude_settings_json: Path,
    project_claude_config_json: Path,
    project_claude_state_json: Path,
    project_anthropic_snapshot_settings_json: Path,
    project_anthropic_snapshot_config_json: Path,
    project_anthropic_snapshot_state_json: Path,
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
    legacy_claude_settings_json: Path,
    legacy_claude_config_json: Path,
    legacy_claude_state_json: Path,
) -> ProjectProviderBootstrapResult:
    source_name = ""
    changed = False

    reference_source_config: Path | None = None
    if agent_cli_config_toml.exists() or agent_cli_auth_json.exists():
        source_name = "agent_cli_home"
        reference_source_config = agent_cli_config_toml
    elif legacy_compat_config_toml.exists() or legacy_compat_auth_json.exists():
        source_name = "legacy_compat_home"
        reference_source_config = legacy_compat_config_toml

    if (
        not project_config_toml.exists()
        and reference_source_config is not None
        and reference_source_config.exists()
    ):
        changed = _copy_file_if_present(reference_source_config, project_config_toml) or changed
    if (
        not project_openai_provider_toml.exists()
        and reference_source_config is not None
        and reference_source_config.exists()
    ):
        changed = (
            _copy_file_if_present(reference_source_config, project_openai_provider_toml) or changed
        )

    if not project_claude_settings_json.exists():
        changed = (
            _copy_file_if_present(legacy_claude_settings_json, project_claude_settings_json)
            or changed
        )
    if not project_claude_config_json.exists():
        changed = (
            _copy_file_if_present(legacy_claude_config_json, project_claude_config_json) or changed
        )
    if not project_claude_state_json.exists():
        changed = (
            _copy_file_if_present(legacy_claude_state_json, project_claude_state_json) or changed
        )

    if not project_anthropic_snapshot_settings_json.exists():
        changed = (
            _copy_file_if_present(
                legacy_claude_settings_json, project_anthropic_snapshot_settings_json
            )
            or changed
        )
    if not project_anthropic_snapshot_config_json.exists():
        changed = (
            _copy_file_if_present(legacy_claude_config_json, project_anthropic_snapshot_config_json)
            or changed
        )
    if not project_anthropic_snapshot_state_json.exists():
        changed = (
            _copy_file_if_present(legacy_claude_state_json, project_anthropic_snapshot_state_json)
            or changed
        )

    return ProjectProviderBootstrapResult(
        bootstrapped=changed,
        source_name=source_name,
    )
