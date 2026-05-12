from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs_projection_name_helpers_runtime import (
    append_unique_names,
    claude_code_powershell_visible,
    project_command_tool_names,
    project_model_facing_provider_names,
    rename_spec,
)
from cli.agent_cli.providers.tool_specs_projection_payload_helpers_runtime import (
    project_model_facing_provider_specs,
)
from cli.agent_cli.providers.tool_specs_projection_spec_helpers_runtime import (
    claude_code_command_specs,
    claude_code_edit_spec,
    claude_code_glob_spec,
    claude_code_grep_spec,
    claude_code_read_spec,
    claude_code_web_fetch_spec,
    claude_code_web_search_spec,
    claude_code_write_spec,
)

FunctionNameFromSpec = Callable[[Any], str]
FunctionTool = Callable[..., Dict[str, Any]]
ProviderDescription = Callable[[str], str]
ResolveToolSurfaceProfile = Callable[[ProviderConfig], str]

__all__ = [
    "FunctionNameFromSpec",
    "FunctionTool",
    "ProviderDescription",
    "ResolveToolSurfaceProfile",
    "append_unique_names",
    "claude_code_command_specs",
    "claude_code_edit_spec",
    "claude_code_glob_spec",
    "claude_code_grep_spec",
    "claude_code_powershell_visible",
    "claude_code_read_spec",
    "claude_code_web_fetch_spec",
    "claude_code_web_search_spec",
    "claude_code_write_spec",
    "project_command_tool_names",
    "project_model_facing_provider_names",
    "project_model_facing_provider_specs",
    "rename_spec",
]
