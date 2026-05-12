from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent


def result_from_tool_event(
    *,
    assistant_text: str,
    event: ToolEvent,
    result_from_event: Callable[..., CommandExecutionResult],
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    if arguments is None:
        return result_from_event(
            assistant_text,
            event,
            tool_name=tool_name,
        )
    return result_from_event(
        assistant_text,
        event,
        tool_name=tool_name,
        arguments=arguments,
    )


def structured_result_with_fallback(
    *,
    structured_owner: Any,
    structured_method_name: str,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    result_from_tool_event_fn: Callable[..., CommandExecutionResult],
    assistant_text: str,
    event_call: Callable[..., ToolEvent],
    tool_name: str,
    structured_args: tuple[Any, ...] = (),
    structured_kwargs: dict[str, Any] | None = None,
    event_args: tuple[Any, ...] = (),
    event_kwargs: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    structured = call_structured_helper(
        structured_owner,
        structured_method_name,
        *structured_args,
        **(structured_kwargs or {}),
    )
    if structured is not None:
        return structured
    return result_from_tool_event_fn(
        assistant_text=assistant_text,
        event=event_call(*event_args, **(event_kwargs or {})),
        result_from_event=result_from_event,
        tool_name=tool_name,
        arguments=arguments,
    )


def build_office_skills_result(
    *,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_skills_call: Callable[[], ToolEvent],
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=office_tools_factory(),
        structured_method_name="list_skills_result",
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="List Office and PDF skills.",
        event_call=office_skills_call,
        tool_name="office_skills",
    )


def build_office_run_result(
    *,
    skill_name: str,
    args: dict[str, Any] | None,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_run_call: Callable[..., ToolEvent],
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
    office_run_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=office_tools_factory(),
        structured_method_name="run_skill_result",
        structured_args=(skill_name,),
        structured_kwargs=args,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="Run Office or PDF skill.",
        event_call=office_run_call,
        event_args=(skill_name,),
        event_kwargs={"args": args},
        tool_name="office_run",
        arguments=office_run_arguments_fn(skill_name, args),
    )


def build_view_image_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_image_call: Callable[[str], ToolEvent],
    result_from_tool_event_fn: Callable[..., CommandExecutionResult],
    view_image_arguments_fn: Callable[[str], dict[str, Any]],
) -> CommandExecutionResult:
    return result_from_tool_event_fn(
        assistant_text="View local image.",
        event=view_image_call(path),
        result_from_event=result_from_event,
        tool_name="view_image",
        arguments=view_image_arguments_fn(path),
    )


def build_view_document_result(
    *,
    path: str,
    mode: str,
    max_chars: int,
    offset: int,
    result_from_event: Callable[..., CommandExecutionResult],
    view_document_call: Callable[..., ToolEvent],
    result_from_tool_event_fn: Callable[..., CommandExecutionResult],
    view_document_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return result_from_tool_event_fn(
        assistant_text="View local document.",
        event=view_document_call(path, mode=mode, max_chars=max_chars, offset=offset),
        result_from_event=result_from_event,
        tool_name="view_document",
        arguments=view_document_arguments_fn(
            path=path,
            mode=mode,
            max_chars=max_chars,
            offset=offset,
        ),
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
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
    policy_doc_import_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=internal_policy_tools_factory(),
        structured_method_name="policy_doc_import_result",
        structured_args=(path,),
        structured_kwargs={"library_root": library_root, "recursive": recursive},
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="Import policy documents.",
        event_call=policy_doc_import_call,
        event_args=(path,),
        event_kwargs={"library_root": library_root, "recursive": recursive},
        tool_name="policy_doc_import",
        arguments=policy_doc_import_arguments_fn(
            path=path,
            library_root=library_root,
            recursive=recursive,
        ),
    )


def build_policy_doc_list_result(
    *,
    library_root: str | None,
    limit: int,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_list_call: Callable[..., ToolEvent],
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
    policy_doc_list_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=internal_policy_tools_factory(),
        structured_method_name="policy_doc_list_result",
        structured_kwargs={"library_root": library_root, "limit": limit},
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="List policy documents.",
        event_call=policy_doc_list_call,
        event_kwargs={"library_root": library_root, "limit": limit},
        tool_name="policy_doc_list",
        arguments=policy_doc_list_arguments_fn(
            library_root=library_root,
            limit=limit,
        ),
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
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
    policy_doc_search_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=internal_policy_tools_factory(),
        structured_method_name="policy_doc_search_result",
        structured_args=(query,),
        structured_kwargs={"library_root": library_root, "limit": limit},
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="Search policy documents.",
        event_call=policy_doc_search_call,
        event_args=(query,),
        event_kwargs={"library_root": library_root, "limit": limit},
        tool_name="policy_doc_search",
        arguments=policy_doc_search_arguments_fn(
            query=query,
            library_root=library_root,
            limit=limit,
        ),
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
    structured_result_with_fallback_fn: Callable[..., CommandExecutionResult],
    policy_doc_read_arguments_fn: Callable[..., dict[str, Any]],
) -> CommandExecutionResult:
    return structured_result_with_fallback_fn(
        structured_owner=internal_policy_tools_factory(),
        structured_method_name="policy_doc_read_result",
        structured_kwargs={
            "doc_id": doc_id,
            "path": path,
            "library_root": library_root,
            "max_chars": max_chars,
        },
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        assistant_text="Read policy document markdown.",
        event_call=policy_doc_read_call,
        event_kwargs={
            "doc_id": doc_id,
            "path": path,
            "library_root": library_root,
            "max_chars": max_chars,
        },
        tool_name="policy_doc_read",
        arguments=policy_doc_read_arguments_fn(
            doc_id=doc_id,
            path=path,
            library_root=library_root,
            max_chars=max_chars,
        ),
    )


__all__ = [
    "build_office_run_result",
    "build_office_skills_result",
    "build_policy_doc_import_result",
    "build_policy_doc_list_result",
    "build_policy_doc_read_result",
    "build_policy_doc_search_result",
    "build_view_document_result",
    "build_view_image_result",
    "result_from_tool_event",
    "structured_result_with_fallback",
]
