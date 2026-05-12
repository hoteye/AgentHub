from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.planner_postprocessing import concise_answer_prompt_text
from cli.agent_cli.providers.platform_guidance import (
    native_directory_snapshot_guidance,
    structured_directory_snapshot_guidance,
)


def planner_init_state(
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
    plugin_manager_factory: Optional[Callable[[], Any]],
    command_text_patterns_fn: Callable[..., Any],
    provider_tool_names_fn: Callable[..., Any],
    minimal_provider_tool_names_fn: Callable[..., Any],
    plugin_prompt_addendum_fn: Callable[..., str],
) -> Dict[str, Any]:
    command_pattern, followup_command_pattern = command_text_patterns_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )
    available_tool_names = ", ".join(
        provider_tool_names_fn(
            config,
            host_platform,
            plugin_manager_factory=plugin_manager_factory,
        )
    )
    native_available_tool_names = ", ".join(
        minimal_provider_tool_names_fn(
            config,
            host_platform,
            plugin_manager_factory=plugin_manager_factory,
        )
    )
    shared_prompt = (
        "You are the built-in assistant for AgentHub CLI. "
        "Respond in concise Chinese. "
        "When the user's request should be handled by a local command or slash command, "
        "return an executable intent instead of telling the user to type it manually. "
        "When tools are available, call tools directly and do not emit slash commands in free-form text. "
        "Primary built-in local commands are /exec_command <cmd>, /write_stdin <session_id> [chars], "
        "/shell <command>, /apply_patch <patch>, "
        "/grep_files <pattern> [--include <glob>] [--path <dir>] [--limit <n>], "
        "/read_file <file_path> [--offset <line>] [--limit <n>], "
        "/list_dir [dir_path] [--offset <n>] [--limit <n>] [--depth <n>], "
        "/office_skills, /office_run <skill> --path <file>, "
        "/web_search <query> [--limit <n>] [--domains <a.com,b.com>] [--recency-days <n>] [--market <cc>], "
        "/web_fetch <url> [--max-chars <n>], /open <url-or-ref-id> [--line <n>], /click <ref-id> <id>, "
        "and /find <ref-id> <pattern>. "
        "Legacy compatibility aliases also exist: /file_list, /file_search, and /file_read. "
        "For local workspace files, prefer grep_files, list_dir, and read_file. "
        "The canonical local inspection trio order is grep_files, list_dir, then read_file. "
        f"{structured_directory_snapshot_guidance(host_platform)}"
        "Treat file_search, file_read, and file_list as compatibility aliases only. "
        "Do not choose the file_* aliases unless the user explicitly uses them or compatibility is required. "
        "When the user asks to inspect, check, or answer questions about the current project, repository, or workspace, "
        "use local file tools first and ground the answer in repository files instead of replying only from generic guidance. "
        "For command execution, prefer exec_command and write_stdin. Use /shell only as a legacy fallback. "
        "Plugin slash commands may also be available when exposed by the host. "
        f"The current host platform is {host_platform.os} ({host_platform.family}). "
        f"Use commands that match this host. "
        "Examples: list current directory files -> /list_dir . --depth 1; "
        "search workspace for a symbol -> /grep_files 'symbol' --path src --limit 20; "
        "read one source slice -> /read_file src/app.py --offset 120 --limit 80; "
        f"show current directory -> {host_platform.shell_command(host_platform.print_working_dir_command)}; "
        f"python version -> {host_platform.shell_command(host_platform.python_version_command)}. "
        "Structured local attachments may appear in an ATTACHMENTS_JSON block inside the user message. "
        "Treat those attachment objects as the authoritative file inputs for the current turn. "
        "When the user asks where a prompt, error, or status text is generated, search for the exact literal text "
        "or a distinctive fragment, and identify the function that defines or assembles that text rather than a "
        "wrapper that only prints surrounding status. "
        f"{concise_answer_prompt_text()} "
    )
    native_shared_prompt = (
        "You are the built-in assistant for AgentHub CLI. "
        "Respond in concise Chinese. "
        "When tools are available, call tools directly instead of telling the user to run commands manually. "
        "Use only the structured tools exposed in this native Responses loop. "
        "For local workspace inspection and command execution, prefer exec_command and write_stdin. "
        f"{native_directory_snapshot_guidance(host_platform)}"
        "When the user asks to inspect, check, or answer questions about the current project, repository, or workspace, "
        "use local tools first and ground the answer in repository files instead of replying only from generic guidance. "
        "Use web_search only for current information or sources outside the local workspace. "
        f"The current host platform is {host_platform.os} ({host_platform.family}). "
        "Use commands that match this host. "
        "Structured local attachments may appear in an ATTACHMENTS_JSON block inside the user message. "
        "Treat those attachment objects as the authoritative file inputs for the current turn. "
        "When the user asks where a prompt, error, or status text is generated, search for the exact literal text "
        "or a distinctive fragment, and identify the function that defines or assembles that text rather than a "
        "wrapper that only prints surrounding status. "
        "When tools are available, first send a brief assistant message about the next concrete action, then call tools. "
        "Keep that pre-tool message concise and practical, and do not expose raw chain-of-thought. "
        "After tools finish, return plain concise Chinese text. "
        "Do not wrap the final answer in JSON. "
        f"{concise_answer_prompt_text()} "
    )
    system_prompt = (
        shared_prompt
        + "Return strict JSON with keys assistant_text, command_text, status_hint. "
        + "Set command_text to null when no command should run. "
        + "Do not wrap the JSON in markdown fences."
    )
    native_tool_system_prompt = native_shared_prompt
    if available_tool_names:
        tool_name_prompt = f" Available structured tool/command names in this session: {available_tool_names}."
        system_prompt += tool_name_prompt
    if native_available_tool_names:
        native_tool_name_prompt = (
            f" Available structured tool/command names in this native Responses loop: "
            f"{native_available_tool_names}."
        )
        native_tool_system_prompt += native_tool_name_prompt
    plugin_prompt = plugin_prompt_addendum_fn(plugin_manager_factory=plugin_manager_factory)
    if plugin_prompt:
        system_prompt += " " + plugin_prompt
    return {
        "command_pattern": command_pattern,
        "followup_command_pattern": followup_command_pattern,
        "system_prompt": system_prompt,
        "native_tool_system_prompt": native_tool_system_prompt,
    }
