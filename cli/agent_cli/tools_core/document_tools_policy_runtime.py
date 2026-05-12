from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import document_tools_projection_helpers_runtime


def policy_doc_import(
    *,
    path: str,
    library_root: Optional[str] = None,
    recursive: bool = True,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = internal_policy_tools_factory().policy_doc_import(
        path,
        library_root=library_root,
        recursive=recursive,
    )
    return document_tools_projection_helpers_runtime.build_policy_doc_import_event(
        payload=payload,
        event_factory=event_factory,
    )


def policy_doc_list(
    *,
    library_root: Optional[str] = None,
    limit: int = 50,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = internal_policy_tools_factory().policy_doc_list(library_root=library_root, limit=limit)
    return document_tools_projection_helpers_runtime.build_policy_doc_list_event(
        payload=payload,
        event_factory=event_factory,
    )


def policy_doc_search(
    *,
    query: str,
    library_root: Optional[str] = None,
    limit: int = 10,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = internal_policy_tools_factory().policy_doc_search(
        query,
        library_root=library_root,
        limit=limit,
    )
    return document_tools_projection_helpers_runtime.build_policy_doc_search_event(
        payload=payload,
        event_factory=event_factory,
    )


def policy_doc_read(
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = internal_policy_tools_factory().policy_doc_read(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
    )
    return document_tools_projection_helpers_runtime.build_policy_doc_read_event(
        payload=payload,
        event_factory=event_factory,
    )


def policy_doc_import_result(
    *,
    path: str,
    library_root: Optional[str] = None,
    recursive: bool = True,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_import_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_policy_doc_import_result(
        path=path,
        library_root=library_root,
        recursive=recursive,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_import_call=policy_doc_import_call,
    )


def policy_doc_list_result(
    *,
    library_root: Optional[str] = None,
    limit: int = 50,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_list_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_policy_doc_list_result(
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_list_call=policy_doc_list_call,
    )


def policy_doc_search_result(
    *,
    query: str,
    library_root: Optional[str] = None,
    limit: int = 10,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_policy_doc_search_result(
        query=query,
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_search_call=policy_doc_search_call,
    )


def policy_doc_read_result(
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_read_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_policy_doc_read_result(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_read_call=policy_doc_read_call,
    )
