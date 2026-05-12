from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.builtin_provider_delegation_specs import (
    canonical_delegation_tool_name,
    delegation_tool_spec_order,
    delegation_tool_specs,
    delegation_tool_specs_by_name,
    visible_delegation_tool_order,
)
from cli.agent_cli.providers.builtin_provider_tool_specs import (
    builtin_provider_tool_specs,
    function_tool,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig


def _provider_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
    )


def _host_platform() -> HostPlatform:
    return HostPlatform(
        family="unix",
        os="linux",
        shell_kind="bash",
        shell_program="/bin/bash",
        list_dir_command="ls -la",
        print_working_dir_command="pwd",
        python_version_command="python -V",
    )


def _provider_description(name: str) -> str:
    return f"desc:{name}"


def _provider_action_names(name: str) -> tuple[str, ...]:
    if name == "browser":
        return ("open", "click")
    return ()


def test_delegation_specs_list_projection_matches_by_name_factory_order() -> None:
    order = delegation_tool_spec_order()
    by_name = delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=_provider_description,
    )
    projected = delegation_tool_specs(
        function_tool=function_tool,
        provider_description=_provider_description,
    )

    assert set(by_name) == set(order)
    assert [item["function"]["name"] for item in projected] == list(order)
    assert projected == [dict(by_name[name]) for name in order]


def test_builtin_provider_delegation_specs_keep_order_and_schema_parity() -> None:
    order = delegation_tool_spec_order()
    order_set = set(order)
    delegation_by_name = delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=_provider_description,
    )
    specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: SimpleNamespace(
            main_loop_spec_kind="function"
        ),
        browser_provider_actions=("open",),
    )

    builtin_by_name = {
        item["function"]["name"]: item for item in specs if item.get("type") == "function"
    }
    builtin_function_names = [
        item["function"]["name"] for item in specs if item.get("type") == "function"
    ]
    delegation_names_from_builtin = [name for name in builtin_function_names if name in order_set]

    assert delegation_names_from_builtin == list(order)
    for name in order:
        assert builtin_by_name[name] == delegation_by_name[name]


def test_visible_delegation_tool_order_tracks_codex_and_claude_profile_differences() -> None:
    assert visible_delegation_tool_order(tool_surface_profile="codex_openai") == (
        "spawn_agent",
        "request_orchestration",
        "spawn_child_tab",
        "send_child_tab",
        "wait_child_tasks",
        "send_input",
        "resume_agent",
        "wait",
        "close_agent",
    )
    assert visible_delegation_tool_order(tool_surface_profile="claude_code") == (
        "Agent",
        "request_orchestration",
        "spawn_child_tab",
        "send_child_tab",
        "wait_child_tasks",
        "SendMessage",
    )
    assert canonical_delegation_tool_name("wait") == "wait_agent"
    assert canonical_delegation_tool_name("Agent") == "spawn_agent"
    assert canonical_delegation_tool_name("SendMessage") == "send_input"


def test_codex_wait_projection_uses_ids_schema() -> None:
    by_name = delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=_provider_description,
        tool_surface_profile="codex_openai",
    )

    wait_spec = by_name["wait"]["function"]["parameters"]

    assert wait_spec["required"] == ["ids"]
    assert sorted(wait_spec["properties"].keys()) == ["ids", "timeout_ms"]


def test_visible_child_tab_delegation_specs_are_model_facing_tools() -> None:
    by_name = delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=_provider_description,
    )

    spawn_child = by_name["spawn_child_tab"]["function"]["parameters"]
    send_child = by_name["send_child_tab"]["function"]["parameters"]
    wait_child = by_name["wait_child_tasks"]["function"]["parameters"]

    assert spawn_child["required"] == ["task"]
    assert "task_name" in spawn_child["properties"]
    assert send_child["required"] == ["target", "message"]
    assert wait_child["properties"]["timeout_ms"]["type"] == "integer"
    assert wait_child["properties"]["wait_for"]["enum"] == ["all", "any"]
