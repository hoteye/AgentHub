from __future__ import annotations

from pathlib import Path
from typing import Mapping

from cli.agent_cli.runtime_paths import PROJECT_LOCAL_DATA_DIR_CANDIDATES
from cli.agent_cli.ui import presentation_mapping_runtime
from cli.agent_cli.ui import presentation_runtime
from cli.agent_cli.workspace_context import AGENT_CLI_HOME, LEGACY_COMPAT_HOME, merge_nested_mappings


DEFAULT_LOCALE = "en"
AUTO_LOCALE = "auto"


def normalize_locale_id(value: str | None) -> str | None:
    return presentation_runtime.normalize_locale_id(value, auto_locale=AUTO_LOCALE)


def detect_system_locale(*, env: Mapping[str, str] | None = None) -> str:
    return presentation_runtime.detect_system_locale(
        env=env,
        auto_locale=AUTO_LOCALE,
        default_locale=DEFAULT_LOCALE,
    )


def format_large_paste_placeholder(char_count: int, index: int, messages: object) -> str:
    return presentation_runtime.format_large_paste_placeholder(char_count, index, messages)


def _read_toml_mapping(path: Path) -> dict[str, object]:
    return presentation_runtime.read_toml_mapping(path)


def _presentation_home_candidates() -> list[Path]:
    return presentation_mapping_runtime.presentation_home_candidates(
        agent_cli_home=AGENT_CLI_HOME,
        legacy_compat_home=LEGACY_COMPAT_HOME,
    )


def user_presentation_config_path() -> Path:
    return AGENT_CLI_HOME / "config.toml"


def _presentation_project_paths(cwd: str | Path | None) -> list[Path]:
    return presentation_runtime.presentation_project_paths(
        cwd,
        project_local_data_dir_candidates=PROJECT_LOCAL_DATA_DIR_CANDIDATES,
    )


def _presentation_config(cwd: str | Path | None) -> dict[str, object]:
    return presentation_mapping_runtime.presentation_config(
        cwd,
        presentation_home_candidates_fn=_presentation_home_candidates,
        presentation_project_paths_fn=_presentation_project_paths,
        read_toml_mapping_fn=_read_toml_mapping,
        merge_nested_mappings_fn=merge_nested_mappings,
    )


def _configured_cli_lang(config: Mapping[str, object]) -> str | None:
    return presentation_runtime.configured_cli_lang(config, auto_locale=AUTO_LOCALE)


def _configured_cli_theme(config: Mapping[str, object]) -> str:
    return presentation_runtime.configured_cli_theme(config)


def _configured_cli_idle_cat(config: Mapping[str, object]) -> bool:
    return presentation_runtime.configured_cli_idle_cat(config)


def _quoted_toml_string(value: str) -> str:
    return presentation_runtime.quoted_toml_string(value)


def _upsert_toml_string_key(
    existing: str,
    *,
    dotted_key: str,
    section_header: str,
    key: str,
    value: str,
) -> str:
    return presentation_runtime.upsert_toml_string_key(
        existing,
        dotted_key=dotted_key,
        section_header=section_header,
        key=key,
        value=value,
    )


def save_user_presentation_preferences(*, lang: str | None = None, theme_id: str | None = None) -> Path:
    return presentation_runtime.save_user_presentation_preferences(
        path=user_presentation_config_path(),
        lang=lang,
        theme_id=theme_id,
    )


def project_presentation_override_path(*, cwd: str | Path | None, setting: str) -> Path | None:
    return presentation_runtime.project_presentation_override_path(
        cwd=cwd,
        setting=setting,
        presentation_project_paths_fn=_presentation_project_paths,
        read_toml_mapping_fn=_read_toml_mapping,
        configured_cli_lang_fn=_configured_cli_lang,
        configured_cli_theme_fn=_configured_cli_theme,
    )
