from __future__ import annotations

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.slash_commands_i18n_runtime import (
    localized_slash_command_description,
    localized_slash_help_advanced_hint,
    localized_slash_help_heading,
    slash_command_description_key,
)
from cli.agent_cli.slash_commands_normalization_helpers_runtime import (
    plugin_command_specs,
    registry_module,
)
from cli.agent_cli.slash_commands_pure_helpers_runtime import (
    BUSY_MODE_BY_COMMAND,
    DISCOVERABLE_SLASH_COMMAND_NAMES,
    SLASH_COMMAND_SPECS,
    SlashCommandSpec,
)
from cli.agent_cli.slash_surface import surface_usage_text


def slash_command_registry_entries(
    *,
    plugin_manager: PluginManager | None = None,
    include_plugins: bool = True,
    discoverable_only: bool = False,
    locale: str | None = None,
):
    command_registry = registry_module()
    busy_availability = {
        name: command_registry.CommandAvailability(busy_mode=busy_mode)
        for name, busy_mode in BUSY_MODE_BY_COMMAND.items()
    }
    builtin_specs = tuple(
        SlashCommandSpec(
            name=spec.name,
            usage=surface_usage_text(spec.name, spec.usage),
            description=localized_slash_command_description(
                spec.name,
                spec.description,
                locale=locale,
            ),
            description_key=slash_command_description_key(spec.name),
        )
        for spec in SLASH_COMMAND_SPECS
        if not getattr(spec, "hidden", False)
        and (
            not discoverable_only
            or str(getattr(spec, "name", "") or "").strip().lower()
            in DISCOVERABLE_SLASH_COMMAND_NAMES
        )
    )
    return command_registry.build_command_registry(
        builtin_specs=builtin_specs,
        plugin_specs=(
            plugin_command_specs(plugin_manager)
            if include_plugins and not discoverable_only
            else []
        ),
        builtin_busy_availability=busy_availability,
    )


def to_legacy_slash_specs(entries) -> list[SlashCommandSpec]:
    return [
        SlashCommandSpec(
            name=entry.name,
            usage=entry.usage,
            description=entry.description,
            description_key=entry.description_key,
        )
        for entry in entries
    ]


def slash_command_registry_rows(
    *,
    plugin_manager: PluginManager | None = None,
    discoverable_only: bool = True,
    locale: str | None = None,
) -> list[dict[str, str]]:
    command_registry = registry_module()
    return command_registry.command_registry_rows(
        slash_command_registry_entries(
            plugin_manager=plugin_manager,
            discoverable_only=discoverable_only,
            locale=locale,
        )
    )


def builtin_slash_command_registry_rows(
    *,
    discoverable_only: bool = True,
    locale: str | None = None,
) -> list[dict[str, str]]:
    command_registry = registry_module()
    return command_registry.command_registry_rows(
        slash_command_registry_entries(
            include_plugins=False,
            discoverable_only=discoverable_only,
            locale=locale,
        )
    )


def slash_command_name_from_text(text_or_name: str) -> str | None:
    """Extract normalized slash command name from raw input or plain name."""
    command_registry = registry_module()
    return command_registry.command_name_from_text(text_or_name)


def slash_command_available_during_busy(text_or_name: str) -> bool:
    """Return busy-time availability for a slash raw input or command name."""
    command_registry = registry_module()
    return command_registry.command_available_during_busy(
        text_or_name,
        slash_command_registry_entries(include_plugins=False),
    )


def slash_command_specs(
    *,
    plugin_manager: PluginManager | None = None,
    discoverable_only: bool = True,
    locale: str | None = None,
) -> list[SlashCommandSpec]:
    return to_legacy_slash_specs(
        slash_command_registry_entries(
            plugin_manager=plugin_manager,
            discoverable_only=discoverable_only,
            locale=locale,
        )
    )


def slash_command_help_text(
    *,
    plugin_manager: PluginManager | None = None,
    include_advanced: bool = False,
    locale: str | None = None,
) -> str:
    command_registry = registry_module()
    entries = slash_command_registry_entries(
        plugin_manager=plugin_manager,
        discoverable_only=not include_advanced,
        locale=locale,
    )
    text = command_registry.command_help_text(
        entries,
        heading=localized_slash_help_heading(locale=locale),
    )
    if not include_advanced:
        text = f"{text}\n\n{localized_slash_help_advanced_hint(locale=locale)}"
    return text


def slash_command_all_help_text(
    *,
    plugin_manager: PluginManager | None = None,
    locale: str | None = None,
) -> str:
    command_registry = registry_module()
    return command_registry.command_help_text(
        slash_command_registry_entries(
            plugin_manager=plugin_manager,
            discoverable_only=False,
            locale=locale,
        ),
        heading=localized_slash_help_heading(locale=locale),
    )


def match_slash_commands(
    prefix: str,
    *,
    plugin_manager: PluginManager | None = None,
    discoverable_only: bool = True,
    locale: str | None = None,
) -> list[SlashCommandSpec]:
    command_registry = registry_module()
    matches = command_registry.match_command_registry(
        prefix,
        slash_command_registry_entries(
            plugin_manager=plugin_manager,
            discoverable_only=discoverable_only,
            locale=locale,
        ),
    )
    return to_legacy_slash_specs(matches)


def autocomplete_slash_command(
    prefix: str,
    *,
    plugin_manager: PluginManager | None = None,
    discoverable_only: bool = True,
) -> str | None:
    command_registry = registry_module()
    return command_registry.autocomplete_command_registry(
        prefix,
        slash_command_registry_entries(
            plugin_manager=plugin_manager,
            discoverable_only=discoverable_only,
        ),
    )
