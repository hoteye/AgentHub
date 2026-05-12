from __future__ import annotations

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.models import ResponseInputItem, compose_turn_events_from_response_items, response_message_item
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs import (
    provider_tool_names,
    responses_minimal_provider_tool_names,
    responses_provider_tool_specs,
)


def test_claude_code_surface_keeps_write_stdin_as_continuation_tool_on_unix() -> None:
    host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )

    provider_names = provider_tool_names(config, host_platform, plugin_manager_factory=lambda: None)
    minimal_names = responses_minimal_provider_tool_names(
        config,
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    response_names = [
        item.get("name")
        for item in responses_provider_tool_specs(
            config,
            host_platform,
            plugin_manager_factory=lambda: None,
        )
        if item.get("type") == "function"
    ]

    assert provider_names[:3] == ["Bash", "write_stdin", "Agent"]
    assert minimal_names[:3] == ["Bash", "write_stdin", "Agent"]
    assert "Bash" in response_names
    assert "write_stdin" in response_names
    assert "Agent" in response_names
    assert "exec_command" not in response_names


def test_claude_code_surface_keeps_write_stdin_as_continuation_tool_on_windows() -> None:
    host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )

    provider_names = provider_tool_names(config, host_platform, plugin_manager_factory=lambda: None)
    minimal_names = responses_minimal_provider_tool_names(
        config,
        host_platform,
        plugin_manager_factory=lambda: None,
    )

    assert provider_names[:4] == ["Bash", "PowerShell", "write_stdin", "Agent"]
    assert minimal_names[:4] == ["Bash", "PowerShell", "write_stdin", "Agent"]


def test_provider_shell_items_project_to_command_execution_turn_events() -> None:
    turn_events = compose_turn_events_from_response_items(
        assistant_text="最终答案",
        response_items=[
            ResponseInputItem(
                item_type="shell_call",
                content="",
                extra={
                    "call_id": "call_shell_1",
                    "status": "completed",
                    "action": {
                        "type": "exec",
                        "command": ["python", "-V"],
                        "timeout_ms": 1000,
                    },
                },
            ),
            ResponseInputItem(
                item_type="shell_call_output",
                content="",
                extra={
                    "call_id": "call_shell_1",
                    "status": "completed",
                    "output": [
                        {
                            "stdout": "Python 3.13.0\n",
                            "stderr": "",
                            "outcome": {"type": "exit", "exit_code": 0},
                        }
                    ],
                },
            ),
            response_message_item("assistant", "最终答案", phase="final_answer"),
        ],
    )

    completed_items = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed" and isinstance(event.get("item"), dict)
    ]
    assert [item["type"] for item in completed_items] == [
        "command_execution",
        "command_execution",
        "agent_message",
    ]
    assert completed_items[0]["id"] == "call_shell_1"
    assert completed_items[0]["command"] == "python -V"
    assert completed_items[1]["aggregated_output"] == "Python 3.13.0\n"
    assert completed_items[1]["exit_code"] == 0
