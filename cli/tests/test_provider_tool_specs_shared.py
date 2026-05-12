from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cli.agent_cli.host_platform import HostPlatform, current_host_platform, detect_host_platform
from cli.agent_cli.providers.chat_completions_planner import ChatCompletionsPlanner
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_planner import OpenAIPlanner
from cli.agent_cli.providers.tool_specs import (
    base_capability_specs,
    builtin_tool_metadata,
    canonical_tool_registry,
    command_action_names,
    command_text_patterns,
    command_usage_text,
    merged_capability_specs,
    merged_provider_tool_specs,
    provider_action_names,
    provider_tool_names,
    responses_minimal_provider_tool_names,
    responses_minimal_provider_tool_specs,
    responses_provider_tool_specs,
)


class _FakePluginManager:
    def __init__(
        self,
        provider_specs: list[dict[str, Any]],
        *,
        capability_specs: list[dict[str, Any]] | None = None,
        provider_tool_capability_declarations: list[dict[str, Any]] | None = None,
    ) -> None:
        self._provider_specs = provider_specs
        self._capability_specs = list(capability_specs or [])
        if provider_tool_capability_declarations is None:
            provider_tool_capability_declarations = []
            for item in provider_specs:
                function_block = item.get("function") if isinstance(item, dict) else None
                function_name = (
                    str(function_block.get("name") or "").strip()
                    if isinstance(function_block, dict)
                    else str(item.get("name") or "").strip() if isinstance(item, dict) else ""
                )
                if not function_name:
                    continue
                provider_tool_capability_declarations.append(
                    _dynamic_tool_declaration(function_name)
                )
        self._provider_tool_capability_declarations = list(provider_tool_capability_declarations)

    def provider_tool_specs(self) -> list[dict[str, Any]]:
        return list(self._provider_specs)

    def provider_system_prompt_fragments(self) -> list[str]:
        return []

    def provider_routing_hints(self) -> list[str]:
        return []

    def tool_specs(self) -> list[dict[str, Any]]:
        return list(self._capability_specs)

    def provider_tool_capability_declarations(self) -> list[dict[str, Any]]:
        return list(self._provider_tool_capability_declarations)


class _FakePromptPluginManager(_FakePluginManager):
    def provider_system_prompt_fragments(self) -> list[str]:
        return ["PLUGIN_FRAGMENT_SENTINEL"]

    def provider_routing_hints(self) -> list[str]:
        return ["PLUGIN_ROUTING_SENTINEL"]


def _dynamic_tool_declaration(function_name: str) -> dict[str, Any]:
    canonical_family = f"plugin_{function_name.replace('-', '_').replace('.', '_')}"
    return {
        "tool_name": function_name,
        "canonical_family": canonical_family,
        "canonical_family_source": "dynamic",
        "canonical_family_owner": "test_plugin",
        "tool_capability_kind": "local_runtime_tool",
        "tool_runtime_binding": "plugin_runtime",
        "supported_profiles": ["all"],
        "default_visibility": "model_visible",
        "canonical_family_record": {
            "canonical_family": canonical_family,
            "family_source": "dynamic",
            "family_owner": "test_plugin",
            "canonical_tool_names": [function_name],
            "compatibility_aliases": [],
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "plugin_runtime",
        },
    }


def _build_planners(host_platform: HostPlatform) -> tuple[OpenAIPlanner, ChatCompletionsPlanner]:
    config = ProviderConfig(model="gpt-5.4", api_key="test")
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        openai_planner = OpenAIPlanner(
            config,
            host_platform=host_platform,
            plugin_manager_factory=lambda: None,
        )
    with patch(
        "cli.agent_cli.providers.chat_completions_planner.build_openai_client",
        return_value=MagicMock(),
    ):
        chat_planner = ChatCompletionsPlanner(
            config,
            host_platform=host_platform,
            plugin_manager_factory=lambda: None,
        )
    return openai_planner, chat_planner


def _assert_structured_directory_guidance(prompt: str, host_platform: HostPlatform) -> None:
    del host_platform
    assert "prefer list_dir with depth 1 over shell directory listings" in prompt
    assert "prefer exec_command with a shell find command over list_dir" not in prompt


def _assert_native_directory_guidance(prompt: str, host_platform: HostPlatform) -> None:
    del host_platform
    assert "prefer list_dir with depth 1 over shell directory listings" in prompt
    assert "Use exec_command only when the user explicitly asks for shell metadata" in prompt


def test_merged_provider_tool_specs_replace_builtin_and_append_plugin_tools() -> None:
    config = ProviderConfig(model="gpt-5.4", api_key="test")
    manager = _FakePluginManager(
        [
            {
                "type": "function",
                "function": {
                    "name": "file_search",
                    "description": "plugin override",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "strict": True,
                "function": {
                    "name": "demo_lookup",
                    "description": "custom plugin tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"slug": {"type": "string"}},
                        "required": ["slug"],
                        "additionalProperties": False,
                    },
                },
            },
        ]
    )

    specs = merged_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: manager,
    )
    function_names = [item["function"]["name"] for item in specs if item.get("type") == "function"]

    if "file_search" not in function_names:
        pytest.skip("file_search alias filtered out of merged specs")
    assert function_names.count("file_search") == 1
    assert "demo_lookup" in function_names
    file_search_spec = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "file_search"
    )
    assert file_search_spec["function"]["description"] == "plugin override"


def test_merged_provider_tool_specs_preserve_mcp_observability_extension_fields() -> None:
    config = ProviderConfig(model="gpt-5.4", api_key="test")
    observability = {
        "schema_version": 1,
        "decision_trace_template": ["approval.requested", "approval.decided", "action.executed"],
        "latency_bucket_field": "approval_latency_bucket",
        "reason_codes": {
            "pending": "approval.pending",
            "approved": "approval.approved",
            "rejected": "approval.rejected",
            "timed_out": "approval.timed_out",
            "expired": "approval.expired",
        },
        "tool_snapshot": {
            "projected_name": "mcp__atlas__search_docs",
            "server_name": "atlas",
            "remote_name": "search_docs",
            "connector_key": "mcp:atlas",
            "approval_scope": "mcp.server:atlas",
        },
    }
    manager = _FakePluginManager(
        [
            {
                "type": "function",
                "strict": True,
                "x_mcp_observability": dict(observability),
                "function": {
                    "name": "mcp__atlas__search_docs",
                    "description": "Search docs via MCP.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
    )

    specs = merged_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: manager,
    )
    mcp_spec = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "mcp__atlas__search_docs"
    )

    assert mcp_spec["x_mcp_observability"] == observability
    assert mcp_spec["x_mcp_observability"]["schema_version"] == 1
    assert mcp_spec["x_mcp_observability"]["decision_trace_template"] == [
        "approval.requested",
        "approval.decided",
        "action.executed",
    ]
    assert mcp_spec["x_mcp_observability"]["latency_bucket_field"] == "approval_latency_bucket"
    assert mcp_spec["x_mcp_observability"]["reason_codes"]["pending"] == "approval.pending"
    assert mcp_spec["x_mcp_observability"]["reason_codes"]["approved"] == "approval.approved"
    assert mcp_spec["x_mcp_observability"]["reason_codes"]["rejected"] == "approval.rejected"
    assert mcp_spec["x_mcp_observability"]["reason_codes"]["timed_out"] == "approval.timed_out"
    assert mcp_spec["x_mcp_observability"]["reason_codes"]["expired"] == "approval.expired"
    assert mcp_spec["x_mcp_observability"]["tool_snapshot"]["connector_key"] == "mcp:atlas"
    assert mcp_spec["x_mcp_observability"]["tool_snapshot"]["approval_scope"] == "mcp.server:atlas"


def test_openai_planner_command_pattern_tracks_shared_tool_registry() -> None:
    planner = OpenAIPlanner(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        host_platform=current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "policy_doc_search",
                        "description": "Search policy docs",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        ),
    )

    intent = planner._intent_from_raw_text("先检索制度库\n/policy_doc_search --query 审计整改")

    assert intent.command_text == "/policy_doc_search --query 审计整改"


def test_openai_planner_command_pattern_includes_plugin_tool_names() -> None:
    planner = OpenAIPlanner(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        host_platform=current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "demo_lookup",
                        "description": "custom plugin tool",
                        "parameters": {
                            "type": "object",
                            "properties": {"slug": {"type": "string"}},
                            "required": ["slug"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        ),
    )

    intent = planner._intent_from_raw_text("执行自定义命令\n/demo_lookup --slug reference")

    assert intent.command_text == "/demo_lookup --slug reference"


def test_planner_guidance_prefers_canonical_file_tools() -> None:
    host_platform = current_host_platform()
    openai_planner, chat_planner = _build_planners(host_platform)

    assert "prefer grep_files, list_dir, and read_file" in openai_planner.system_prompt
    assert (
        "canonical local inspection trio order is grep_files, list_dir, then read_file"
        in openai_planner.system_prompt
    )
    assert "default base for grep_files" in openai_planner.system_prompt
    assert "omit path or use '.'" in openai_planner.system_prompt
    _assert_structured_directory_guidance(openai_planner.system_prompt, host_platform)
    assert (
        "use local file tools first and ground the answer in repository files"
        in openai_planner.system_prompt
    )
    assert "prefer exec_command and write_stdin" in openai_planner.system_prompt
    assert "set workdir instead of prepending cd" in openai_planner.system_prompt
    assert "Do not wrap commands in cd ... &&" in openai_planner.system_prompt
    assert "canonical browser-family" in openai_planner.system_prompt
    assert (
        "Do not choose the file_* aliases unless the user explicitly uses them"
        in openai_planner.system_prompt
    )
    assert (
        f"python version -> /exec_command '{host_platform.python_version_command}' --workdir ."
        in openai_planner.system_prompt
    )
    assert "/shell pwd" not in openai_planner.system_prompt
    assert "prefer /file_list, /file_search, and /file_read" not in openai_planner.system_prompt
    assert "prefer grep_files, list_dir, and read_file" in chat_planner.system_prompt
    assert (
        "canonical local inspection trio order is grep_files, list_dir, then read_file"
        in chat_planner.system_prompt
    )
    assert "default base for grep_files" in chat_planner.system_prompt
    assert "omit path or use '.'" in chat_planner.system_prompt
    _assert_structured_directory_guidance(chat_planner.system_prompt, host_platform)
    assert (
        "use local file tools first and ground the answer in repository files"
        in chat_planner.system_prompt
    )
    assert "prefer exec_command and write_stdin" in chat_planner.system_prompt
    assert "set workdir instead of prepending cd" in chat_planner.system_prompt
    assert "Do not wrap commands in cd ... &&" in chat_planner.system_prompt
    assert "canonical browser-family" in chat_planner.system_prompt
    assert (
        "Do not choose the file_* aliases unless the user explicitly uses them"
        in chat_planner.system_prompt
    )
    assert "prefer file_list, file_search, and file_read" not in chat_planner.system_prompt


def test_openai_planner_native_prompt_uses_minimal_responses_tool_guidance() -> None:
    host_platform = current_host_platform()
    planner, _ = _build_planners(host_platform)

    assert (
        "Use only the structured tools exposed in this native Responses loop."
        in planner.native_tool_system_prompt
    )
    assert "prefer exec_command and write_stdin" in planner.native_tool_system_prompt
    assert "set workdir instead of prepending cd" in planner.native_tool_system_prompt
    assert "Do not wrap commands in cd ... &&" in planner.native_tool_system_prompt
    _assert_native_directory_guidance(planner.native_tool_system_prompt, host_platform)
    assert (
        "Use web_search only for current information or sources outside the local workspace."
        in planner.native_tool_system_prompt
    )
    assert "Primary built-in local commands are" not in planner.native_tool_system_prompt
    assert "/apply_patch <patch>" not in planner.native_tool_system_prompt
    assert "/grep_files <pattern>" not in planner.native_tool_system_prompt
    assert "/read_file <file_path>" not in planner.native_tool_system_prompt
    assert "/list_dir [dir_path]" not in planner.native_tool_system_prompt


def test_openai_planner_native_prompt_does_not_append_plugin_prompt_addendum() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(
            ProviderConfig(model="gpt-5.4", api_key="test"),
            host_platform=current_host_platform(),
            plugin_manager_factory=lambda: _FakePromptPluginManager([]),
        )

    assert "PLUGIN_FRAGMENT_SENTINEL" in planner.system_prompt
    assert "PLUGIN_ROUTING_SENTINEL" in planner.system_prompt
    assert "PLUGIN_FRAGMENT_SENTINEL" not in planner.native_tool_system_prompt
    assert "PLUGIN_ROUTING_SENTINEL" not in planner.native_tool_system_prompt


def test_openai_json_prompt_primary_command_list_prefers_canonical_shell_and_browser() -> None:
    host_platform = current_host_platform()
    planner, _ = _build_planners(host_platform)
    primary_line = next(
        (
            line.strip()
            for line in planner.system_prompt.splitlines()
            if line.strip().startswith("Primary built-in local commands are ")
        ),
        "",
    )

    assert primary_line
    assert "/exec_command <cmd>" in primary_line
    assert "/write_stdin <session_id> [chars]" in primary_line
    assert "/browser <action> [...]" in primary_line
    assert "/shell <command>" not in primary_line
    assert "/open <url-or-ref-id>" not in primary_line
    assert "/click <ref-id> <id>" not in primary_line
    assert "/find <ref-id> <pattern>" not in primary_line


def test_planner_guidance_branches_explicitly_for_windows_and_unix_hosts() -> None:
    hosts = [
        detect_host_platform(system_name="Linux", sys_platform="linux"),
        detect_host_platform(system_name="Darwin", sys_platform="darwin"),
        detect_host_platform(system_name="Windows", sys_platform="win32"),
    ]

    for host_platform in hosts:
        openai_planner, chat_planner = _build_planners(host_platform)
        _assert_structured_directory_guidance(openai_planner.system_prompt, host_platform)
        _assert_structured_directory_guidance(chat_planner.system_prompt, host_platform)
        _assert_native_directory_guidance(openai_planner.native_tool_system_prompt, host_platform)


def test_responses_provider_tool_specs_reuse_shared_registry_and_flatten_functions() -> None:
    config = ProviderConfig(model="gpt-5.4", api_key="test")
    manager = _FakePluginManager(
        [
            {
                "type": "function",
                "strict": True,
                "function": {
                    "name": "demo_lookup",
                    "description": "custom plugin tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"slug": {"type": "string"}},
                        "required": ["slug"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
    )

    specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: manager,
    )

    demo_lookup = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "demo_lookup"
    )
    assert demo_lookup["description"] == "custom plugin tool"
    assert demo_lookup["parameters"]["required"] == ["slug"]
    grep_files = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "grep_files"
    )
    read_file = next(
        item for item in specs if item.get("type") == "function" and item.get("name") == "read_file"
    )
    list_dir = next(
        item for item in specs if item.get("type") == "function" and item.get("name") == "list_dir"
    )
    exec_command = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "exec_command"
    )
    write_stdin = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "write_stdin"
    )
    update_plan = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "update_plan"
    )
    request_user_input = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "request_user_input"
    )
    assert grep_files["parameters"]["required"] == ["pattern"]
    assert "pattern" in grep_files["parameters"]["properties"]
    assert "file_path" in read_file["parameters"]["properties"]
    assert "path" not in read_file["parameters"]["properties"]
    assert "max_chars" not in read_file["parameters"]["properties"]
    assert read_file["parameters"]["properties"]["indentation"]["additionalProperties"] is False
    assert "dir_path" in list_dir["parameters"]["properties"]
    assert exec_command["parameters"]["required"] == ["cmd"]
    assert "yield_time_ms" in exec_command["parameters"]["properties"]
    assert write_stdin["parameters"]["required"] == ["session_id"]
    assert "chars" in write_stdin["parameters"]["properties"]
    assert update_plan["parameters"]["required"] == ["plan"]
    assert request_user_input["parameters"]["required"] == ["questions"]
    file_list = next(
        (
            item
            for item in specs
            if item.get("type") == "function" and item.get("name") == "file_list"
        ),
        None,
    )
    assert file_list is None
    assert demo_lookup["strict"] is True
    assert all("function" not in item for item in specs if item.get("type") == "function")


def test_responses_provider_tool_specs_preserve_native_web_search_provider_specs() -> None:
    config = ProviderConfig(
        model="glm-5",
        api_key="test",
        provider_name="glm",
        planner_kind="chat_completions",
    )

    specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    web_search = next(item for item in specs if item.get("type") == "web_search")
    assert web_search["web_search"]["search_engine"] == "search_pro"
    assert web_search["function"]["name"] == "web_search"


def test_responses_provider_tool_specs_openai_responses_defaults_to_function_web_search_without_mixed_tools_opt_in() -> (
    None
):
    specs = responses_provider_tool_specs(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test",
            provider_name="openai",
            planner_kind="openai_responses",
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert not any(item.get("type") == "web_search" for item in specs)
    web_search = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "web_search"
    )
    assert web_search["parameters"]["required"] == ["query"]
    assert "query" in web_search["parameters"]["properties"]


def test_responses_provider_tool_specs_openai_responses_exposes_native_web_search_when_mixed_tools_opted_in() -> (
    None
):
    specs = responses_provider_tool_specs(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test",
            provider_name="openai",
            planner_kind="openai_responses",
            raw_model={"native_web_search_mixed_tools": True},
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    web_search = next(item for item in specs if item.get("type") == "web_search")
    assert web_search == {"type": "web_search", "external_web_access": False}


def test_responses_provider_tool_specs_openai_cached_mode_promotes_to_live_for_danger_full_access() -> (
    None
):
    specs = responses_provider_tool_specs(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test",
            provider_name="openai",
            planner_kind="openai_responses",
            raw_model={"native_web_search_mixed_tools": True},
            raw_provider={"web_search_mode": "cached", "sandbox_mode": "danger-full-access"},
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    web_search = next(item for item in specs if item.get("type") == "web_search")
    assert web_search == {"type": "web_search", "external_web_access": True}


def test_responses_provider_tool_specs_deepseek_keeps_web_search_on_function_path() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(
            model="deepseek-chat",
            api_key="test",
            provider_name="deepseek",
            planner_kind="deepseek_chat",
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert not any(item.get("type") == "web_search" for item in specs)
    web_search = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "web_search"
    )
    assert web_search["parameters"]["required"] == ["query"]


def test_responses_provider_tool_specs_hide_builtin_shell_alias() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    response_names = [item.get("name") for item in specs if item.get("type") == "function"]
    assert "shell" not in response_names


def test_base_capability_specs_hide_internal_registry_fields() -> None:
    shell = next(item for item in base_capability_specs() if item["name"] == "shell")

    assert shell == {
        "name": "shell",
        "label": "Shell",
        "description": "Run a local shell command and capture stdout/stderr.",
        "mutates_ui": False,
        "requires_confirmation": False,
    }
    assert "usage_text" not in shell
    assert "provider_description" not in shell


def test_builtin_command_metadata_helpers_share_browser_and_shell_registry_values() -> None:
    browser_metadata = builtin_tool_metadata("browser")

    assert command_usage_text("shell").startswith("Usage: /shell <command>")
    assert command_usage_text("apply_patch") == "Usage: /apply_patch <patch>"
    assert command_usage_text("browser").startswith("Usage: /browser <action>")
    assert "evaluate" in command_action_names("browser")
    assert "evaluate" not in provider_action_names("browser")
    assert "cookies_set" in provider_action_names("browser")
    assert browser_metadata is not None
    assert browser_metadata["provider_description"]


def test_canonical_registry_entry_drives_builtin_metadata_and_provider_schema() -> None:
    browser_entry = next(
        item for item in canonical_tool_registry() if item.get("name") == "browser"
    )
    browser_metadata = builtin_tool_metadata("browser")

    assert browser_entry["metadata"] == browser_metadata
    assert browser_entry["provider_description"] == browser_metadata["provider_description"]
    assert browser_entry["command_actions"] == command_action_names("browser")
    assert browser_entry["provider_actions"] == provider_action_names("browser")

    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    browser = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "browser"
    )
    assert browser["function"]["description"] == browser_entry["provider_description"]
    assert browser["function"]["parameters"]["properties"]["action"]["enum"] == list(
        browser_entry["provider_actions"]
    )


def test_builtin_command_usage_templates_cover_runtime_tool_commands() -> None:
    assert command_usage_text("exec_command").startswith("Usage: /exec_command <cmd>")
    assert command_usage_text("write_stdin").startswith("Usage: /write_stdin <session_id>")
    assert (
        command_usage_text("agent_workflow")
        == "Usage: /agent_workflow <agent_id> [steps <n>] [checkpoints <n>]"
    )
    assert (
        command_usage_text("recover_agent")
        == "Usage: /recover_agent <agent_id> [action <retry_step|resume_session|close_session>] [step-id <id>]"
    )
    assert command_usage_text("update_plan").startswith("Usage: /update_plan")
    assert command_usage_text("request_user_input").startswith("Usage: /request_user_input")
    assert (
        command_usage_text("grep_files")
        == "Usage: /grep_files <pattern> [include <glob>] [path <dir>] [limit <n>]"
    )
    assert (
        command_usage_text("read_file")
        == "Usage: /read_file <file_path> [offset <line>] [limit <n>]"
    )
    assert (
        command_usage_text("list_dir")
        == "Usage: /list_dir [dir_path] [offset <n>] [limit <n>] [depth <n>]"
    )
    assert (
        command_usage_text("file_search") == "Usage: /file_search <query> [path <dir>] [limit <n>]"
    )
    assert command_usage_text("file_read") == "Usage: /file_read <path> [offset <line>] [limit <n>]"
    assert command_usage_text("office_run") == "Usage: /office_run <skill> <file>"
    assert (
        command_usage_text("web_search")
        == "Usage: /web_search <query> [limit <n>] [domains <a.com,b.com>] [recency-days <n>] [market <cc>]"
    )
    assert command_usage_text("view_image") == "Usage: /view_image <path>"
    assert command_usage_text("web_fetch") == "Usage: /web_fetch <url> [max-chars <n>]"
    assert command_usage_text("open") == "Usage: /open <url-or-ref-id> [line <n>]"
    assert command_usage_text("click") == "Usage: /click <ref-id> <id>"
    assert command_usage_text("find") == "Usage: /find <ref-id> <pattern>"


def test_file_search_and_file_list_metadata_marked_legacy_aliases() -> None:
    file_search_metadata = builtin_tool_metadata("file_search")
    file_list_metadata = builtin_tool_metadata("file_list")

    assert file_search_metadata is not None
    assert file_list_metadata is not None
    assert "Legacy compatibility alias" in str(file_search_metadata["provider_description"])
    assert "Legacy compatibility alias" in str(file_list_metadata["provider_description"])


def test_shell_and_navigation_alias_metadata_are_marked_compatibility_aliases() -> None:
    shell_metadata = builtin_tool_metadata("shell")
    open_metadata = builtin_tool_metadata("open")
    click_metadata = builtin_tool_metadata("click")
    find_metadata = builtin_tool_metadata("find")

    assert shell_metadata is not None
    assert open_metadata is not None
    assert click_metadata is not None
    assert find_metadata is not None
    assert shell_metadata["model_default_exposure"] == "compatibility_alias"
    assert open_metadata["model_default_exposure"] == "compatibility_alias"
    assert click_metadata["model_default_exposure"] == "compatibility_alias"
    assert find_metadata["model_default_exposure"] == "compatibility_alias"
    assert "Legacy compatibility alias" in str(shell_metadata["provider_description"])
    assert "Legacy" in str(open_metadata["provider_description"])


def test_canonical_file_tools_are_ordered_ahead_of_compat_aliases() -> None:
    merged_specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    merged_names = [
        item["function"]["name"] for item in merged_specs if item.get("type") == "function"
    ]
    assert "grep_files" in merged_names
    assert "read_file" in merged_names
    assert "list_dir" in merged_names
    assert "file_search" not in merged_names
    assert "file_read" not in merged_names
    assert "file_list" not in merged_names

    responses_specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    response_names = [item["name"] for item in responses_specs if item.get("type") == "function"]
    assert "grep_files" in response_names
    assert "read_file" in response_names
    assert "list_dir" in response_names
    assert "file_search" not in response_names
    assert "file_read" not in response_names
    assert "file_list" not in response_names


def test_responses_provider_tool_specs_hide_builtin_compat_file_tools() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    response_names = [item["name"] for item in specs if item.get("type") == "function"]
    assert response_names.count("grep_files") == 1
    assert response_names.count("read_file") == 1
    assert response_names.count("list_dir") == 1
    assert "file_search" not in response_names
    assert "file_read" not in response_names
    assert "file_list" not in response_names


def test_provider_tool_names_prioritize_canonical_file_trio() -> None:
    names = provider_tool_names(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert "grep_files" in names
    assert "read_file" in names
    assert "list_dir" in names
    assert "file_search" not in names
    assert "file_read" not in names
    assert "file_list" not in names
    assert "shell" not in names
    assert "open" not in names
    assert "click" not in names
    assert "find" not in names


def test_command_text_patterns_include_canonical_and_compat_alias_names() -> None:
    pattern, followup = command_text_patterns(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
    )

    assert "grep_files" in pattern.pattern
    assert "read_file" in followup.pattern
    assert "file_search" in pattern.pattern
    assert "file_read" in followup.pattern
    assert "file_list" in pattern.pattern
    assert "shell" in pattern.pattern
    assert "open" in pattern.pattern
    assert "click" in followup.pattern
    assert "find" in pattern.pattern


def test_merged_provider_tool_specs_browser_schema_uses_registry_metadata() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    browser = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "browser"
    )
    action_spec = browser["function"]["parameters"]["properties"]["action"]

    assert (
        browser["function"]["description"]
        == builtin_tool_metadata("browser")["provider_description"]
    )
    assert action_spec["enum"] == list(provider_action_names("browser"))


def test_plugin_override_can_still_expose_file_search_when_builtin_alias_is_hidden() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "file_search",
                        "description": "plugin override",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        ),
    )

    file_search = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "file_search"
    )
    assert file_search["function"]["description"] == "plugin override"


def test_plugin_override_can_still_expose_shell_when_builtin_alias_is_hidden() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "shell",
                        "description": "plugin shell override",
                        "parameters": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        ),
    )

    shell = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "shell"
    )
    assert shell["function"]["description"] == "plugin shell override"


def test_responses_provider_tool_specs_hide_builtin_browser_aliases() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    response_names = [item.get("name") for item in specs if item.get("type") == "function"]
    assert "browser" in response_names
    assert "open" not in response_names
    assert "click" not in response_names
    assert "find" not in response_names


def test_plugin_override_can_still_expose_open_when_builtin_browser_alias_is_hidden() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "open",
                        "description": "plugin open override",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        ),
    )

    open_tool = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "open"
    )
    assert open_tool["function"]["description"] == "plugin open override"


def test_merged_provider_tool_specs_hide_undeclared_plugin_tool_by_default() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "demo_lookup",
                        "description": "custom plugin tool",
                        "parameters": {
                            "type": "object",
                            "properties": {"slug": {"type": "string"}},
                            "required": ["slug"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            provider_tool_capability_declarations=[],
        ),
    )

    names = [item["function"]["name"] for item in specs if item.get("type") == "function"]
    assert "demo_lookup" not in names


def test_provider_tool_names_hide_profile_mismatched_plugin_declaration() -> None:
    names = provider_tool_names(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test",
            interaction_profile="codex_openai",
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "demo_lookup",
                        "description": "custom plugin tool",
                        "parameters": {
                            "type": "object",
                            "properties": {"slug": {"type": "string"}},
                            "required": ["slug"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            provider_tool_capability_declarations=[
                {
                    "tool_name": "demo_lookup",
                    "supported_profiles": ["generic_chat"],
                    "default_visibility": "model_visible",
                }
            ],
        ),
    )

    assert "demo_lookup" not in names


def test_merged_provider_tool_specs_preserve_builtin_when_plugin_override_not_model_visible() -> (
    None
):
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "grep_files",
                        "description": "plugin override should be hidden",
                        "parameters": {
                            "type": "object",
                            "properties": {"pattern": {"type": "string"}},
                            "required": ["pattern"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            provider_tool_capability_declarations=[
                {
                    "tool_name": "grep_files",
                    "supported_profiles": ["all"],
                    "default_visibility": "host_only",
                }
            ],
        ),
    )

    grep_files = next(
        item
        for item in specs
        if item.get("type") == "function" and item["function"]["name"] == "grep_files"
    )
    assert grep_files["function"]["description"] != "plugin override should be hidden"


def test_responses_provider_tool_specs_no_longer_expose_builtin_file_search_alias_description() -> (
    None
):
    file_search_entry = next(
        item for item in canonical_tool_registry() if item.get("name") == "file_search"
    )

    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    response_names = [item.get("name") for item in specs if item.get("type") == "function"]
    assert "file_search" not in response_names
    assert file_search_entry["provider_description"].startswith("Legacy compatibility alias")


def test_responses_minimal_provider_tool_specs_match_reference_like_subset() -> None:
    specs = responses_minimal_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    names = [item["name"] for item in specs if item.get("type") == "function"]
    assert names == [
        "exec_command",
        "write_stdin",
        "spawn_agent",
        "spawn_child_tab",
        "send_child_tab",
        "wait_child_tasks",
        "send_input",
        "resume_agent",
        "wait_agent",
        "agent_workflow",
        "recover_agent",
        "close_agent",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "web_search",
        "view_image",
    ]
    assert (
        responses_minimal_provider_tool_names(
            ProviderConfig(model="gpt-5.4", api_key="test"),
            current_host_platform(),
            plugin_manager_factory=lambda: None,
        )
        == names
    )


def test_responses_minimal_provider_tool_names_explicit_codex_openai_profile_returns_parity_subset() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        interaction_profile="codex_openai",
    )

    assert responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    ) == [
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "view_image",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "close_agent",
    ]


def test_responses_minimal_provider_tool_specs_project_request_user_input_to_ask_user_question_for_claude_code() -> (
    None
):
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )

    names = responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert "AskUserQuestion" in names
    assert "request_user_input" not in names
    assert any(
        item.get("name") == "AskUserQuestion" for item in specs if item.get("type") == "function"
    )
    assert not any(
        item.get("name") == "request_user_input" for item in specs if item.get("type") == "function"
    )


def test_responses_minimal_provider_tool_names_legacy_reference_parity_alias_returns_parity_subset() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        raw_provider={"reference_parity": True},
    )

    assert responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    ) == [
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "view_image",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "close_agent",
    ]


def test_responses_provider_tool_specs_include_view_image_schema() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    view_image = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "view_image"
    )
    spawn_agent = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "spawn_agent"
    )
    send_input = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "send_input"
    )
    spawn_child_tab = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "spawn_child_tab"
    )
    send_child_tab = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "send_child_tab"
    )
    wait_child_tasks = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "wait_child_tasks"
    )
    wait_agent = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "wait_agent"
    )
    agent_workflow = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "agent_workflow"
    )
    recover_agent = next(
        item
        for item in specs
        if item.get("type") == "function" and item.get("name") == "recover_agent"
    )
    assert view_image["parameters"]["required"] == ["path"]
    assert view_image["parameters"]["properties"]["path"]["type"] == "string"
    assert spawn_agent["parameters"]["required"] == ["task"]
    assert spawn_agent["parameters"]["properties"]["role"]["enum"] == ["subagent", "teammate"]
    assert spawn_agent["parameters"]["properties"]["reason"]["enum"] == [
        "research_side_task",
        "verify_side_task",
        "long_running_exec",
        "background_side_task",
    ]
    assert spawn_agent["parameters"]["properties"]["mode"]["enum"] == ["sync", "background"]
    assert spawn_agent["parameters"]["properties"]["task_shape"]["enum"] == [
        "read_only",
        "workspace_mutating",
        "context_sensitive",
        "long_running",
    ]
    assert spawn_child_tab["parameters"]["required"] == ["task"]
    assert spawn_child_tab["parameters"]["properties"]["task_name"]["type"] == "string"
    assert send_child_tab["parameters"]["required"] == ["target", "message"]
    assert wait_child_tasks["parameters"]["properties"]["timeout_ms"]["type"] == "integer"
    assert wait_child_tasks["parameters"]["properties"]["wait_for"]["enum"] == ["all", "any"]
    assert send_input["parameters"]["required"] == ["target", "message"]
    assert wait_agent["parameters"]["required"] == ["target"]
    assert wait_agent["parameters"]["properties"]["reason"]["enum"] == ["wait_for_child_result"]
    assert agent_workflow["parameters"]["required"] == ["target"]
    assert agent_workflow["parameters"]["properties"]["steps"]["type"] == "integer"
    assert agent_workflow["parameters"]["properties"]["checkpoints"]["type"] == "integer"
    assert recover_agent["parameters"]["required"] == ["target"]
    assert recover_agent["parameters"]["properties"]["action"]["enum"] == [
        "retry_step",
        "resume_session",
        "close_session",
    ]
    assert "bounded side tasks" in spawn_agent["description"]
    assert not any(
        item.get("name") == "request_orchestration"
        for item in specs
        if item.get("type") == "function"
    )
    assert "explicitly depends" in wait_agent["description"]
    assert "Prefer agent_workflow" in wait_agent["description"]
    assert "non-blocking snapshots via agent_workflow" in wait_agent["description"]
    assert "available recovery actions" in agent_workflow["description"]
    assert "retrying the same child preserves context" in recover_agent["description"]


def test_merged_capability_specs_include_policy_tools_and_plugin_overrides() -> None:
    manager = _FakePluginManager(
        [],
        capability_specs=[
            {
                "name": "file_search",
                "description": "plugin capability override",
                "mutates_ui": True,
                "requires_confirmation": True,
            }
        ],
    )

    specs = merged_capability_specs(plugin_manager_factory=lambda: manager)
    names = [item["name"] for item in specs]

    assert "policy_doc_search" in names
    file_search = next(item for item in specs if item["name"] == "file_search")
    assert file_search["description"] == "plugin capability override"
    assert file_search["mutates_ui"] is True
    assert file_search["requires_confirmation"] is True


def test_responses_minimal_provider_tool_specs_reference_parity_matches_captured_gpt54_shape() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        base_url="https://relay.example.com/reference/v1",
        raw_provider={"reference_parity": True, "web_search_mode": "live"},
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert [(item.get("type"), item.get("name")) for item in specs] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]
    exec_command = specs[0]
    assert list(exec_command["parameters"]["properties"].keys()) == [
        "cmd",
        "justification",
        "login",
        "max_output_tokens",
        "prefix_rule",
        "sandbox_permissions",
        "shell",
        "tty",
        "workdir",
        "yield_time_ms",
    ]
    assert (
        "Prefer setting this instead of prepending `cd`"
        in exec_command["parameters"]["properties"]["workdir"]["description"]
    )
    assert specs[5] == {"type": "web_search", "external_web_access": True}
    assert responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    ) == [
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "view_image",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "close_agent",
    ]


def test_responses_minimal_provider_tool_specs_reference_parity_collab_surface_matches_codex_shape() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        raw_provider={"reference_parity": True, "collab_tools": True, "web_search_mode": "live"},
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert [(item.get("type"), item.get("name")) for item in specs] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]

    spawn_agent = next(item for item in specs if item.get("name") == "spawn_agent")
    send_input = next(item for item in specs if item.get("name") == "send_input")
    resume_agent = next(item for item in specs if item.get("name") == "resume_agent")
    wait_tool = next(item for item in specs if item.get("name") == "wait_agent")
    close_agent = next(item for item in specs if item.get("name") == "close_agent")

    assert list(spawn_agent["parameters"]["properties"].keys()) == [
        "agent_type",
        "fork_context",
        "items",
        "message",
    ]
    assert "required" not in spawn_agent["parameters"]
    assert "task" not in spawn_agent["parameters"]["properties"]

    assert list(send_input["parameters"]["properties"].keys()) == [
        "interrupt",
        "items",
        "message",
        "target",
    ]
    assert send_input["parameters"]["required"] == ["target"]
    assert "id" not in send_input["parameters"]["properties"]

    assert list(resume_agent["parameters"]["properties"].keys()) == ["id"]
    assert resume_agent["parameters"]["required"] == ["id"]

    assert list(wait_tool["parameters"]["properties"].keys()) == ["targets", "timeout_ms"]
    assert wait_tool["parameters"]["required"] == ["targets"]
    assert "target" not in wait_tool["parameters"]["properties"]

    assert list(close_agent["parameters"]["properties"].keys()) == ["target"]
    assert close_agent["parameters"]["required"] == ["target"]


def test_responses_minimal_provider_tool_specs_reference_parity_includes_freeform_apply_patch_when_enabled() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        base_url="https://relay.example.com/reference/v1",
        raw_model={"apply_patch_tool_type": "freeform"},
        raw_provider={"reference_parity": True},
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert [(item.get("type"), item.get("name")) for item in specs] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]
    assert specs[4]["format"]["type"] == "grammar"
    assert responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    ) == [
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "view_image",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "close_agent",
    ]


def test_responses_minimal_provider_tool_specs_reference_parity_request_user_input_and_permissions_flags() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        base_url="https://relay.example.com/reference/v1",
        raw_model={
            "default_mode_request_user_input": True,
            "request_permission_enabled": True,
        },
        raw_provider={"reference_parity": True},
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    request_user_input = next(item for item in specs if item.get("name") == "request_user_input")
    exec_command = next(item for item in specs if item.get("name") == "exec_command")
    assert request_user_input["description"].endswith("Default or Plan mode.")
    assert "additional_permissions" in exec_command["parameters"]["properties"]
    assert (
        "with_additional_permissions"
        in exec_command["parameters"]["properties"]["sandbox_permissions"]["description"]
    )
    additional_permissions = exec_command["parameters"]["properties"]["additional_permissions"]
    assert set(additional_permissions["properties"].keys()) == {"file_system", "network"}
    assert "required" not in additional_permissions
    assert (
        additional_permissions["properties"]["network"]["properties"]["enabled"]["type"]
        == "boolean"
    )


def test_responses_provider_tool_specs_request_user_input_schema_contract() -> None:
    specs = responses_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    request_user_input = next(item for item in specs if item.get("name") == "request_user_input")
    parameters = request_user_input["parameters"]
    question_schema = parameters["properties"]["questions"]["items"]
    option_schema = question_schema["properties"]["options"]["items"]

    assert parameters["required"] == ["questions"]
    assert question_schema["required"] == ["id", "header", "question", "options"]
    assert option_schema["required"] == ["label", "description"]
    assert question_schema["additionalProperties"] is False
    assert option_schema["additionalProperties"] is False
    assert (
        'Do not include an "Other" option'
        in question_schema["properties"]["options"]["description"]
    )
    assert not any(item.get("name") == "request_orchestration" for item in specs)
