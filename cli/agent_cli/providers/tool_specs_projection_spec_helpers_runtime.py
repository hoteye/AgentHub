from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import (
    builtin_provider_tool_specs_catalog_schema_runtime as builtin_provider_tool_specs_catalog_schema_runtime_helpers,
)

FunctionTool = Callable[..., dict[str, Any]]
ProviderDescription = Callable[[str], str]

_BASH_TOOL_NAME = "Bash"
_GLOB_TOOL_NAME = "Glob"
_GREP_TOOL_NAME = "Grep"
_READ_TOOL_NAME = "Read"
_WEB_SEARCH_TOOL_NAME = "WebSearch"
_WEB_FETCH_TOOL_NAME = "WebFetch"
_CLAUDE_WRITE_DESCRIPTION = (
    "Write a workspace file by providing the full file content. "
    "Use Read first before overwriting an existing file. "
    "Prefer Edit for targeted changes to existing files; use Write for new files or full rewrites."
)
_CLAUDE_EDIT_DESCRIPTION = (
    "Edit an existing workspace file by replacing an exact string. "
    "Use Read before editing. "
    "Keep old_string to the smallest clearly unique span; it must match exactly once unless replace_all=true."
)
_CLAUDE_BASH_DESCRIPTION = """Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile.

IMPORTANT: Avoid using this tool to run `find`, `grep`, `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

- File search: Use Glob (NOT find or ls)
- Content search: Use Grep (NOT grep or rg)
- Read files: Use Read (NOT cat/head/tail)
- Edit files: Use Edit (NOT sed/awk)
- Write files: Use Write (NOT echo >/cat <<EOF)
- Communication: Output text directly (NOT echo/printf)

While the Bash tool can do similar things, it's better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission.

# Instructions

- Always quote file paths that contain spaces with double quotes in your command.
- Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it.
- When issuing multiple commands:
  - If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message. Example: if you need to run "git status" and "git diff", send a single message with two Bash tool calls in parallel.
  - If the commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together.
  - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.
  - DO NOT use newlines to separate commands (newlines are ok in quoted strings).
- Avoid unnecessary `sleep` commands."""


def claude_code_powershell_visible(host_platform: HostPlatform) -> bool:
    return str(host_platform.family or "").strip().lower() == "windows"


def claude_code_command_specs(
    host_platform: HostPlatform,
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> list[dict[str, Any]]:
    bash = builtin_provider_tool_specs_catalog_schema_runtime_helpers.bash_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
    _set_spec_description(bash, _CLAUDE_BASH_DESCRIPTION)
    specs = [bash]
    if claude_code_powershell_visible(host_platform):
        specs.append(
            builtin_provider_tool_specs_catalog_schema_runtime_helpers.powershell_spec(
                function_tool=function_tool,
                provider_description=provider_description,
            )
        )
    return specs


def _set_spec_description(spec: dict[str, Any], description: str) -> None:
    function_block = spec.get("function")
    if isinstance(function_block, dict):
        function_block["description"] = description
        return
    spec["description"] = description


def claude_code_write_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    spec = builtin_provider_tool_specs_catalog_schema_runtime_helpers.write_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
    function_block = spec.get("function")
    if not isinstance(function_block, dict):
        return spec
    function_block["description"] = _CLAUDE_WRITE_DESCRIPTION
    parameters = function_block.get("parameters")
    if not isinstance(parameters, dict):
        return spec
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return spec
    file_path = properties.get("file_path")
    if isinstance(file_path, dict):
        file_path["description"] = (
            "Workspace-relative target path to create or overwrite. "
            "If the file already exists, use read_file first."
        )
    content = properties.get("content")
    if isinstance(content, dict):
        content["description"] = "Full file content to write for the create or overwrite operation."
    return spec


def claude_code_edit_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    spec = builtin_provider_tool_specs_catalog_schema_runtime_helpers.edit_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
    function_block = spec.get("function")
    if not isinstance(function_block, dict):
        return spec
    function_block["description"] = _CLAUDE_EDIT_DESCRIPTION
    parameters = function_block.get("parameters")
    if not isinstance(parameters, dict):
        return spec
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return spec
    file_path = properties.get("file_path")
    if isinstance(file_path, dict):
        file_path["description"] = (
            "Workspace-relative target path to edit after reading the current file."
        )
    old_string = properties.get("old_string")
    if isinstance(old_string, dict):
        old_string["description"] = (
            "Exact text to replace from read_file output. "
            "Keep it to the smallest clearly unique span; it must match exactly once unless replace_all=true."
        )
    new_string = properties.get("new_string")
    if isinstance(new_string, dict):
        new_string["description"] = (
            "Replacement text. Preserve exact indentation and surrounding syntax."
        )
    replace_all = properties.get("replace_all")
    if isinstance(replace_all, dict):
        replace_all["description"] = (
            "Set true only when every occurrence of old_string should be replaced."
        )
    return spec


def claude_code_glob_spec(*, function_tool: FunctionTool) -> dict[str, Any]:
    return function_tool(
        name=_GLOB_TOOL_NAME,
        description=(
            "Fast file pattern matching tool that works with any codebase size. "
            "Supports glob patterns like **/*.js or src/**/*.ts. "
            "Returns matching file paths sorted by modification time. "
            "Use this to find files by name patterns. "
            "When doing open-ended searches that may require multiple rounds of globbing and grepping, use the Agent tool instead. "
            "If path is omitted, the current working directory is used."
        ),
        properties={
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files against (e.g. **/*.js, src/**/*.ts)",
            },
            "path": {
                "type": "string",
                "description": (
                    "Directory to search in. If omitted, the current working directory is used. "
                    "Prefer omitting path or using '.' for the current working directory. "
                    "Use an explicit path only when you need repository-wide scope or another directory inside the active workspace/project root. "
                    "For repository-wide file discovery, set path to workspace_root from reference context."
                ),
            },
        },
        required=["pattern"],
    )


def claude_code_grep_spec(*, function_tool: FunctionTool) -> dict[str, Any]:
    return function_tool(
        name=_GREP_TOOL_NAME,
        description=(
            "A powerful search tool built on ripgrep. "
            "Supports full regex syntax. "
            "Filter files with glob parameter or type parameter. "
            "Use this for searching file contents. "
            "Use the Agent tool for open-ended searches requiring multiple rounds. "
            "If path is omitted, the current working directory is used."
        ),
        properties={
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for in file contents",
            },
            "path": {
                "type": "string",
                "description": (
                    "File or directory to search in. If omitted, the current working directory is used. "
                    "Prefer omitting path or using '.' for the current working directory. "
                    "Use an explicit path only when you need repository-wide scope or another directory inside the active workspace/project root. "
                    "For repository-wide file discovery, set path to workspace_root from reference context."
                ),
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. *.js, **/*.tsx)",
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode: content shows matching lines, files_with_matches shows file paths, count shows match counts. Defaults to files_with_matches.",
            },
            "-A": {"type": "number", "description": "Number of lines to show after each match"},
            "-B": {"type": "number", "description": "Number of lines to show before each match"},
            "-C": {
                "type": "number",
                "description": "Number of lines to show before and after each match",
            },
            "-i": {"type": "boolean", "description": "Case insensitive search"},
            "-n": {"type": "boolean", "description": "Show line numbers in output"},
            "head_limit": {
                "type": "number",
                "description": "Limit output to first N lines/entries",
            },
            "offset": {"type": "number", "description": "Skip first N lines/entries"},
            "multiline": {
                "type": "boolean",
                "description": "Enable multiline mode where patterns can span lines",
            },
            "type": {
                "type": "string",
                "description": "File type to search (e.g. js, py, rust, go)",
            },
        },
        required=["pattern"],
    )


def claude_code_read_spec(*, function_tool: FunctionTool) -> dict[str, Any]:
    return function_tool(
        name=_READ_TOOL_NAME,
        description=(
            "Reads a file from the local filesystem. "
            "By default reads up to 2000 lines from the beginning. "
            "Specify offset and limit for large files. "
            "This tool can only read files, not directories. To read a directory, use an ls command via the Bash tool."
        ),
        properties={
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute path to the file to read. "
                    "Keep the path inside the active workspace/project root. "
                    "When the current working directory file is intended, prefer a path under the current directory."
                ),
            },
            "limit": {"type": "number", "description": "Number of lines to read"},
            "offset": {"type": "number", "description": "Line number to start reading from"},
        },
        required=["file_path"],
    )


def claude_code_web_search_spec(*, function_tool: FunctionTool) -> dict[str, Any]:
    return function_tool(
        name=_WEB_SEARCH_TOOL_NAME,
        description=(
            "Searches the web and returns results. "
            "Use for current events, documentation, and information beyond training data."
        ),
        properties={
            "query": {"type": "string", "description": "Search query"},
            "allowed_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include search results from these domains",
            },
            "blocked_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Never include search results from these domains",
            },
        },
        required=["query"],
    )


def claude_code_web_fetch_spec(*, function_tool: FunctionTool) -> dict[str, Any]:
    return function_tool(
        name=_WEB_FETCH_TOOL_NAME,
        description=(
            "Fetches content from a URL and returns it as markdown. "
            "The prompt parameter is accepted as a hint but the full page content is returned."
        ),
        properties={
            "url": {"type": "string", "description": "URL to fetch content from"},
            "prompt": {
                "type": "string",
                "description": "Hint describing what information to look for in the page",
            },
        },
        required=["url"],
    )
