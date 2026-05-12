from __future__ import annotations

from typing import Any, Optional

from cli.agent_cli.tools_core import document_tools_runtime


def policy_doc_import(registry: Any, path: str, *, library_root: Optional[str] = None, recursive: bool = True) -> Any:
    return document_tools_runtime.policy_doc_import(
        path=path,
        library_root=library_root,
        recursive=recursive,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        event_factory=registry._event,
    )


def policy_doc_list(registry: Any, *, library_root: Optional[str] = None, limit: int = 50) -> Any:
    return document_tools_runtime.policy_doc_list(
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        event_factory=registry._event,
    )


def policy_doc_search(registry: Any, query: str, *, library_root: Optional[str] = None, limit: int = 10) -> Any:
    return document_tools_runtime.policy_doc_search(
        query=query,
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        event_factory=registry._event,
    )


def policy_doc_read(
    registry: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> Any:
    return document_tools_runtime.policy_doc_read(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        event_factory=registry._event,
    )


def policy_doc_import_result(registry: Any, path: str, *, library_root: Optional[str] = None, recursive: bool = True) -> Any:
    return document_tools_runtime.policy_doc_import_result(
        path=path,
        library_root=library_root,
        recursive=recursive,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        policy_doc_import_call=registry.policy_doc_import,
    )


def policy_doc_list_result(registry: Any, *, library_root: Optional[str] = None, limit: int = 50) -> Any:
    return document_tools_runtime.policy_doc_list_result(
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        policy_doc_list_call=registry.policy_doc_list,
    )


def policy_doc_search_result(registry: Any, query: str, *, library_root: Optional[str] = None, limit: int = 10) -> Any:
    return document_tools_runtime.policy_doc_search_result(
        query=query,
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        policy_doc_search_call=registry.policy_doc_search,
    )


def policy_doc_read_result(
    registry: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> Any:
    return document_tools_runtime.policy_doc_read_result(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=registry._get_internal_policy_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        policy_doc_read_call=registry.policy_doc_read,
    )
