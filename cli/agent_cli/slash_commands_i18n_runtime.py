from __future__ import annotations

from cli.agent_cli.ui.presentation import DEFAULT_LOCALE, MessageCatalog, normalize_locale_id


def slash_command_description_key(command_name: str) -> str:
    normalized = str(command_name or "").strip().lower().replace("-", "_")
    return f"slash.command.{normalized}.description" if normalized else ""


def localized_message(key: str, fallback: str, *, locale: str | None = None) -> str:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return str(fallback or "")
    normalized_locale = normalize_locale_id(locale) or DEFAULT_LOCALE
    text = MessageCatalog(normalized_locale).text(normalized_key)
    return str(fallback or "") if text == normalized_key else text


def localized_slash_command_description(
    command_name: str,
    fallback: str,
    *,
    locale: str | None = None,
) -> str:
    return localized_message(
        slash_command_description_key(command_name),
        str(fallback or ""),
        locale=locale,
    )


def localized_slash_help_heading(*, locale: str | None = None) -> str:
    return localized_message("slash.help.heading", "available commands:", locale=locale)


def localized_slash_help_advanced_hint(*, locale: str | None = None) -> str:
    return localized_message(
        "slash.help.advanced_hint",
        "Use /help all to show advanced and plugin commands.",
        locale=locale,
    )
