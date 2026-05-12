from __future__ import annotations

from cli.agent_cli.ui import slash_controller_popup_runtime
from cli.agent_cli.ui.presentation import (
    AUTO_LOCALE,
    PresentationSettings,
    detect_system_locale,
    normalize_locale_id,
    project_presentation_override_path,
    resolve_presentation_settings,
)


def resolve_effective_presentation(cwd: str, lang: str, theme_id: str) -> PresentationSettings:
    return resolve_presentation_settings(
        cwd=cwd,
        lang=lang,
        theme_id=theme_id,
    )


def desired_locale_for_preference(value: str) -> str:
    return slash_controller_popup_runtime.desired_locale_for_preference(
        value,
        auto_locale=AUTO_LOCALE,
        detect_system_locale_fn=detect_system_locale,
    )


def lang_override_source(
    presentation_locale: str,
    desired_locale: str,
    presentation_cli_language: str,
    workspace_root: str,
) -> str | None:
    return slash_controller_popup_runtime.lang_override_source(
        presentation_locale=presentation_locale,
        desired_locale=desired_locale,
        presentation_cli_language=presentation_cli_language,
        normalize_locale_id_fn=normalize_locale_id,
        project_override_path_getter=lambda setting: _stringify_override_path(
            workspace_root, setting
        ),
    )


def theme_override_source(
    presentation_theme_id: str,
    desired_theme_id: str,
    presentation_cli_theme_id: str,
    workspace_root: str,
) -> str | None:
    return slash_controller_popup_runtime.theme_override_source(
        presentation_theme_id=presentation_theme_id,
        desired_theme_id=desired_theme_id,
        presentation_cli_theme_id=presentation_cli_theme_id,
        project_override_path_getter=lambda setting: _stringify_override_path(
            workspace_root, setting
        ),
    )


def _stringify_override_path(cwd: str, setting: str) -> str | None:
    override_path = project_presentation_override_path(cwd=cwd, setting=setting)
    return str(override_path) if override_path is not None else None
