from __future__ import annotations

from cli.agent_cli.runtime_core import tool_commands_helper_groups_runtime as _runtime

ToolCommandResult = _runtime.ToolCommandResult

# Re-export public handler names to preserve existing imports and patch points.
handle_glob_files = _runtime.handle_glob_files
handle_plugin_enable = _runtime.handle_plugin_enable
handle_plugin_disable = _runtime.handle_plugin_disable
handle_plugin_reload = _runtime.handle_plugin_reload
handle_plugin_install = _runtime.handle_plugin_install
handle_plugin_remove = _runtime.handle_plugin_remove
handle_grep_files = _runtime.handle_grep_files
handle_list_dir = _runtime.handle_list_dir
handle_read_file = _runtime.handle_read_file
handle_file_list = _runtime.handle_file_list
handle_file_search = _runtime.handle_file_search
handle_file_read = _runtime.handle_file_read
handle_office_skills = _runtime.handle_office_skills
handle_office_run = _runtime.handle_office_run
handle_view_image = _runtime.handle_view_image
handle_open = _runtime.handle_open
handle_click = _runtime.handle_click
handle_find = _runtime.handle_find

__all__ = [
    "ToolCommandResult",
    "handle_glob_files",
    "handle_plugin_enable",
    "handle_plugin_disable",
    "handle_plugin_reload",
    "handle_plugin_install",
    "handle_plugin_remove",
    "handle_grep_files",
    "handle_list_dir",
    "handle_read_file",
    "handle_file_list",
    "handle_file_search",
    "handle_file_read",
    "handle_office_skills",
    "handle_office_run",
    "handle_view_image",
    "handle_open",
    "handle_click",
    "handle_find",
]
