from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cli.agent_cli.ui import presentation_helpers as _presentation_helpers
from cli.agent_cli.ui import presentation_mapping_runtime
from cli.agent_cli.ui import presentation_messages as _presentation_messages
from cli.agent_cli.ui import presentation_runtime
from cli.agent_cli.ui.theme import CliTheme, DEFAULT_THEME_ID, resolve_cli_theme
from cli.agent_cli.workspace_context import AGENT_CLI_HOME, LEGACY_COMPAT_HOME, merge_nested_mappings


DEFAULT_LOCALE = "en"
AUTO_LOCALE = "auto"
SUPPORTED_LOCALES = ("en", "zh-CN", "ja", "fr")

# Keep this module-level name for monkeypatch compatibility.
_MESSAGES: dict[str, dict[str, str]] = _presentation_messages.MESSAGES


@dataclass(frozen=True, slots=True)
class MessageCatalog:
    locale: str

    def text(self, key: str, **kwargs: object) -> str:
        return presentation_mapping_runtime.message_text(
            messages=_MESSAGES,
            key=key,
            locale=self.locale,
            default_locale=DEFAULT_LOCALE,
            kwargs=kwargs,
        )


@dataclass(frozen=True, slots=True)
class PresentationSettings:
    locale: str
    theme_id: str
    theme: CliTheme
    messages: MessageCatalog
    idle_cat_enabled: bool


def default_messages() -> MessageCatalog:
    return MessageCatalog(DEFAULT_LOCALE)


normalize_locale_id = _presentation_helpers.normalize_locale_id
detect_system_locale = _presentation_helpers.detect_system_locale
format_large_paste_placeholder = _presentation_helpers.format_large_paste_placeholder
_read_toml_mapping = _presentation_helpers._read_toml_mapping
_presentation_project_paths = _presentation_helpers._presentation_project_paths
_configured_cli_lang = _presentation_helpers._configured_cli_lang
_configured_cli_theme = _presentation_helpers._configured_cli_theme
_configured_cli_idle_cat = _presentation_helpers._configured_cli_idle_cat
_quoted_toml_string = _presentation_helpers._quoted_toml_string
_upsert_toml_string_key = _presentation_helpers._upsert_toml_string_key
project_presentation_override_path = _presentation_helpers.project_presentation_override_path


def _presentation_home_candidates() -> list[Path]:
    return presentation_mapping_runtime.presentation_home_candidates(
        agent_cli_home=AGENT_CLI_HOME,
        legacy_compat_home=LEGACY_COMPAT_HOME,
    )


def user_presentation_config_path() -> Path:
    return AGENT_CLI_HOME / "config.toml"


def _presentation_config(cwd: str | Path | None) -> dict[str, object]:
    return presentation_mapping_runtime.presentation_config(
        cwd,
        presentation_home_candidates_fn=_presentation_home_candidates,
        presentation_project_paths_fn=_presentation_project_paths,
        read_toml_mapping_fn=_read_toml_mapping,
        merge_nested_mappings_fn=merge_nested_mappings,
    )


def save_user_presentation_preferences(*, lang: str | None = None, theme_id: str | None = None) -> Path:
    return presentation_runtime.save_user_presentation_preferences(
        path=user_presentation_config_path(),
        lang=lang,
        theme_id=theme_id,
    )


def resolve_presentation_settings(
    *,
    cwd: str | Path | None = None,
    lang: str | None = None,
    theme_id: str | None = None,
) -> PresentationSettings:
    return presentation_runtime.resolve_presentation_settings(
        cwd=cwd,
        lang=lang,
        theme_id=theme_id,
        auto_locale=AUTO_LOCALE,
        default_locale=DEFAULT_LOCALE,
        supported_locales=SUPPORTED_LOCALES,
        presentation_config_fn=_presentation_config,
        configured_cli_lang_fn=_configured_cli_lang,
        configured_cli_theme_fn=_configured_cli_theme,
        configured_cli_idle_cat_fn=_configured_cli_idle_cat,
        normalize_locale_id_fn=normalize_locale_id,
        detect_system_locale_fn=detect_system_locale,
        resolve_cli_theme_fn=resolve_cli_theme,
        message_catalog_type=MessageCatalog,
        presentation_settings_type=PresentationSettings,
        default_theme_id=DEFAULT_THEME_ID,
    )
