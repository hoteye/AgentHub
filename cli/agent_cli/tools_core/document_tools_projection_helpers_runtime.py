from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    document_tools_projection_event_helpers_runtime,
    document_tools_projection_result_helpers_runtime,
)
from cli.agent_cli.tools_core.document_tools_pure_helpers_runtime import (
    office_run_arguments,
    office_run_summary,
    office_skills_summary,
    policy_doc_import_arguments,
    policy_doc_import_summary,
    policy_doc_list_arguments,
    policy_doc_list_summary,
    policy_doc_read_arguments,
    policy_doc_read_summary,
    policy_doc_search_arguments,
    policy_doc_search_summary,
    view_document_arguments,
    view_image_arguments,
    view_image_success_summary,
)


def build_payload_event(
    *,
    tool_name: str,
    payload: dict[str, Any],
    summary: str,
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_payload_event(
        tool_name=tool_name,
        payload=payload,
        summary=summary,
        event_factory=event_factory,
    )


def result_from_tool_event(
    *,
    assistant_text: str,
    event: ToolEvent,
    result_from_event: Callable[..., CommandExecutionResult],
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.result_from_tool_event(
        assistant_text=assistant_text,
        event=event,
        result_from_event=result_from_event,
        tool_name=tool_name,
        arguments=arguments,
    )


def structured_result_with_fallback(
    *,
    structured_owner: Any,
    structured_method_name: str,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    assistant_text: str,
    event_call: Callable[..., ToolEvent],
    tool_name: str,
    structured_args: tuple[Any, ...] = (),
    structured_kwargs: dict[str, Any] | None = None,
    event_args: tuple[Any, ...] = (),
    event_kwargs: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.structured_result_with_fallback(
        structured_owner=structured_owner,
        structured_method_name=structured_method_name,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        result_from_tool_event_fn=result_from_tool_event,
        assistant_text=assistant_text,
        event_call=event_call,
        tool_name=tool_name,
        structured_args=structured_args,
        structured_kwargs=structured_kwargs,
        event_args=event_args,
        event_kwargs=event_kwargs,
        arguments=arguments,
    )


# Keep wrappers at this facade so monkeypatches against this module continue to
# intercept nested builder calls.
def build_office_skills_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_office_skills_event(
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        office_skills_summary_fn=office_skills_summary,
    )


def build_office_skills_result(
    *,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_skills_call: Callable[[], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_office_skills_result(
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_skills_call=office_skills_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
    )


def build_office_run_event(
    *,
    skill_name: str,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_office_run_event(
        skill_name=skill_name,
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        office_run_summary_fn=office_run_summary,
    )


def build_office_run_result(
    *,
    skill_name: str,
    args: dict[str, Any] | None,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_run_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_office_run_result(
        skill_name=skill_name,
        args=args,
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_run_call=office_run_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
        office_run_arguments_fn=office_run_arguments,
    )


def build_view_image_event(
    *,
    ok: bool,
    payload: dict[str, Any],
    resolved_name: str,
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_view_image_event(
        ok=ok,
        payload=payload,
        resolved_name=resolved_name,
        event_factory=event_factory,
        view_image_success_summary_fn=view_image_success_summary,
    )


def build_view_image_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_image_call: Callable[[str], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_view_image_result(
        path=path,
        result_from_event=result_from_event,
        view_image_call=view_image_call,
        result_from_tool_event_fn=result_from_tool_event,
        view_image_arguments_fn=view_image_arguments,
    )


def build_view_document_result(
    *,
    path: str,
    mode: str,
    max_chars: int,
    offset: int,
    result_from_event: Callable[..., CommandExecutionResult],
    view_document_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_view_document_result(
        path=path,
        mode=mode,
        max_chars=max_chars,
        offset=offset,
        result_from_event=result_from_event,
        view_document_call=view_document_call,
        result_from_tool_event_fn=result_from_tool_event,
        view_document_arguments_fn=view_document_arguments,
    )


def build_policy_doc_import_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_policy_doc_import_event(
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        policy_doc_import_summary_fn=policy_doc_import_summary,
    )


def build_policy_doc_list_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_policy_doc_list_event(
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        policy_doc_list_summary_fn=policy_doc_list_summary,
    )


def build_policy_doc_search_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_policy_doc_search_event(
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        policy_doc_search_summary_fn=policy_doc_search_summary,
    )


def build_policy_doc_read_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_projection_event_helpers_runtime.build_policy_doc_read_event(
        payload=payload,
        event_factory=event_factory,
        build_payload_event_fn=build_payload_event,
        policy_doc_read_summary_fn=policy_doc_read_summary,
    )


def build_policy_doc_import_result(
    *,
    path: str,
    library_root: str | None,
    recursive: bool,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_import_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_policy_doc_import_result(
        path=path,
        library_root=library_root,
        recursive=recursive,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_import_call=policy_doc_import_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
        policy_doc_import_arguments_fn=policy_doc_import_arguments,
    )


def build_policy_doc_list_result(
    *,
    library_root: str | None,
    limit: int,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_list_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_policy_doc_list_result(
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_list_call=policy_doc_list_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
        policy_doc_list_arguments_fn=policy_doc_list_arguments,
    )


def build_policy_doc_search_result(
    *,
    query: str,
    library_root: str | None,
    limit: int,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_policy_doc_search_result(
        query=query,
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_search_call=policy_doc_search_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
        policy_doc_search_arguments_fn=policy_doc_search_arguments,
    )


def build_policy_doc_read_result(
    *,
    doc_id: str | None,
    path: str | None,
    library_root: str | None,
    max_chars: int,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_read_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_result_helpers_runtime.build_policy_doc_read_result(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_read_call=policy_doc_read_call,
        structured_result_with_fallback_fn=structured_result_with_fallback,
        policy_doc_read_arguments_fn=policy_doc_read_arguments,
    )


__all__ = [
    "build_office_run_event",
    "build_office_run_result",
    "build_office_skills_event",
    "build_office_skills_result",
    "build_payload_event",
    "build_policy_doc_import_event",
    "build_policy_doc_import_result",
    "build_policy_doc_list_event",
    "build_policy_doc_list_result",
    "build_policy_doc_read_event",
    "build_policy_doc_read_result",
    "build_policy_doc_search_event",
    "build_policy_doc_search_result",
    "build_view_document_result",
    "build_view_image_event",
    "build_view_image_result",
    "result_from_tool_event",
    "structured_result_with_fallback",
]
