from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    document_tools_normalization_helpers_runtime,
    document_tools_projection_helpers_runtime,
    document_tools_pure_helpers_runtime,
)


def get_office_tools(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
) -> Any:
    return document_tools_pure_helpers_runtime.load_cached_tool(
        cached_tools=cached_tools,
        load_project_tool_module=load_project_tool_module,
        module_name="office_tools",
        class_name="OfficeFileTools",
    )


def get_internal_policy_tools(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
) -> Any:
    return document_tools_pure_helpers_runtime.load_cached_tool(
        cached_tools=cached_tools,
        load_project_tool_module=load_project_tool_module,
        module_name="internal_policy_tools",
        class_name="InternalPolicyTools",
    )


def office_skills(
    *,
    office_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = office_tools_factory().list_skills()
    return document_tools_projection_helpers_runtime.build_office_skills_event(
        payload=payload,
        event_factory=event_factory,
    )


def office_skills_result(
    *,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_skills_call: Callable[[], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_office_skills_result(
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_skills_call=office_skills_call,
    )


def office_run(
    *,
    skill_name: str,
    args: Optional[Dict[str, Any]] = None,
    office_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    normalized_args = document_tools_normalization_helpers_runtime.normalized_mapping(args)
    payload = office_tools_factory().run_skill(skill_name, **normalized_args)
    return document_tools_projection_helpers_runtime.build_office_run_event(
        skill_name=skill_name,
        payload=payload,
        event_factory=event_factory,
    )


def office_run_result(
    *,
    skill_name: str,
    args: Optional[Dict[str, Any]] = None,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_run_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    normalized_args = document_tools_normalization_helpers_runtime.normalized_mapping(args) or None
    return document_tools_projection_helpers_runtime.build_office_run_result(
        skill_name=skill_name,
        args=normalized_args,
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_run_call=office_run_call,
    )
