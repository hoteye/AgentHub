from __future__ import annotations

from cli.agent_cli.slash_commands_normalization_helpers_runtime import (
    plugin_command_specs as _plugin_command_specs,
    registry_module as _registry_module,
)
from cli.agent_cli.slash_commands_projection_helpers_runtime import (
    autocomplete_slash_command,
    builtin_slash_command_registry_rows,
    match_slash_commands,
    slash_command_available_during_busy,
    slash_command_help_text,
    slash_command_name_from_text,
    slash_command_registry_entries as _slash_command_registry_entries,
    slash_command_registry_rows,
    slash_command_specs,
    to_legacy_slash_specs as _to_legacy_slash_specs,
)
from cli.agent_cli.slash_commands_pure_helpers_runtime import (
    BUSY_MODE_BY_COMMAND as _BUSY_MODE_BY_COMMAND,
    SLASH_COMMAND_SPECS,
    THEME_COMMAND_USAGE,
    SlashCommandSpec,
)
