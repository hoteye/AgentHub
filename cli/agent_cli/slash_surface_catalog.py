from __future__ import annotations

from cli.agent_cli import slash_surface_catalog_keyword_helpers as _keyword_helpers
from cli.agent_cli import slash_surface_catalog_option_helpers as _option_helpers
from cli.agent_cli import slash_surface_catalog_projection_helpers as _projection_helpers
from cli.agent_cli import slash_surface_catalog_usage_helpers as _usage_helpers

SURFACE_USAGE: dict[str, str] = _projection_helpers.project_surface_usage(
    _usage_helpers.SURFACE_USAGE_DATA
)
VALUE_KEYWORDS: dict[str, dict[str, str]] = _projection_helpers.project_keyword_map(
    _keyword_helpers.VALUE_KEYWORDS_DATA
)
BOOLEAN_KEYWORDS: dict[str, dict[str, str]] = _projection_helpers.project_keyword_map(
    _keyword_helpers.BOOLEAN_KEYWORDS_DATA
)
OPTION_VALUES: dict[tuple[str, str], tuple[str, ...]] = _projection_helpers.project_option_value_map(
    _option_helpers.OPTION_VALUES_DATA
)
IMPLICIT_ENUMS: dict[str, dict[str, tuple[str, str | None]]] = _projection_helpers.project_implicit_enum_map(
    _option_helpers.IMPLICIT_ENUMS_DATA
)
RIGHT_BOUNDARY_OPTION_COMMANDS = _projection_helpers.project_command_name_set(
    _option_helpers.RIGHT_BOUNDARY_OPTION_COMMAND_NAMES
)
LEADING_OPTION_COMMANDS = _projection_helpers.project_command_name_set(
    _option_helpers.LEADING_OPTION_COMMAND_NAMES
)
SECOND_POSITION_AS_PATH_COMMANDS = _projection_helpers.project_command_name_set(
    _option_helpers.SECOND_POSITION_AS_PATH_COMMAND_NAMES
)
