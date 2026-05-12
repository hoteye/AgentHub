from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.providers import (
    builtin_provider_delegation_specs_pure_helpers_runtime as pure_helpers,
)

FunctionTool = Callable[..., dict[str, Any]]
ProviderDescription = Callable[[str], str]


def _delegation_spec(
    spec_name: str,
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return function_tool(
        **pure_helpers.delegation_spec_kwargs(
            spec_name,
            provider_description=provider_description,
        )
    )


def canonical_delegation_specs_by_name(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, dict[str, Any]]:
    return {
        "spawn_agent": spawn_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "request_orchestration": request_orchestration_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "spawn_child_tab": spawn_child_tab_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "send_child_tab": send_child_tab_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "wait_child_tasks": wait_child_tasks_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "send_input": send_input_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "resume_agent": resume_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "wait_agent": wait_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "agent_workflow": agent_workflow_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "recover_agent": recover_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
        "close_agent": close_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        ),
    }


def spawn_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "spawn_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def request_orchestration_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "request_orchestration",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def spawn_child_tab_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "spawn_child_tab",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def send_child_tab_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "send_child_tab",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def wait_child_tasks_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "wait_child_tasks",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def send_input_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "send_input",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def resume_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "resume_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def wait_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "wait_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def codex_wait_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "codex_wait",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def claude_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "claude_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def claude_send_message_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "claude_send_message",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def agent_workflow_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "agent_workflow",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def recover_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "recover_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )


def close_agent_spec(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    return _delegation_spec(
        "close_agent",
        function_tool=function_tool,
        provider_description=provider_description,
    )
