from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.providers import (
    builtin_provider_delegation_specs_projection_runtime as projection_runtime,
)
from cli.agent_cli.providers import builtin_provider_delegation_specs_pure_runtime as pure_runtime
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    canonical_delegation_tool_name as _canonical_delegation_tool_name,
)
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    delegation_tool_spec_order as _delegation_tool_spec_order,
)
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    visible_delegation_tool_name as _visible_delegation_tool_name,
)
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    visible_delegation_tool_order as _visible_delegation_tool_order,
)


def delegation_tool_spec_order() -> tuple[str, ...]:
    return _delegation_tool_spec_order()


def canonical_delegation_tool_name(name: str) -> str:
    return _canonical_delegation_tool_name(name)


def visible_delegation_tool_name(
    name: str,
    *,
    tool_surface_profile: str = "",
) -> str:
    return _visible_delegation_tool_name(
        name,
        tool_surface_profile=tool_surface_profile,
    )


def visible_delegation_tool_order(*, tool_surface_profile: str = "") -> tuple[str, ...]:
    return _visible_delegation_tool_order(tool_surface_profile=tool_surface_profile)


def delegation_tool_specs_by_name(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
    tool_surface_profile: str = "",
) -> dict[str, dict[str, Any]]:
    return projection_runtime.delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
        tool_surface_profile=tool_surface_profile,
    )


def delegation_tool_specs(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
    tool_surface_profile: str = "",
) -> list[dict[str, Any]]:
    return projection_runtime.delegation_tool_specs(
        function_tool=function_tool,
        provider_description=provider_description,
        tool_surface_profile=tool_surface_profile,
    )


def spawn_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.spawn_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def request_orchestration_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.request_orchestration_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def spawn_child_tab_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.spawn_child_tab_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def send_child_tab_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.send_child_tab_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def wait_child_tasks_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.wait_child_tasks_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def send_input_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.send_input_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def resume_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.resume_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def wait_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.wait_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def codex_wait_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.codex_wait_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def claude_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.claude_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def claude_send_message_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.claude_send_message_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def agent_workflow_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.agent_workflow_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def recover_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.recover_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def close_agent_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
) -> dict[str, Any]:
    return pure_runtime.close_agent_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
