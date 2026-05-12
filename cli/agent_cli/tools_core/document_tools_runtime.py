from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    document_tools_media_runtime,
    document_tools_office_runtime,
    document_tools_policy_runtime,
    document_tools_pure_helpers_runtime,
    document_tools_view_document_helpers_runtime,
)

_VIEW_IMAGE_UNSUPPORTED_MESSAGE = (
    document_tools_pure_helpers_runtime._VIEW_IMAGE_UNSUPPORTED_MESSAGE
)
_VIEW_DOCUMENT_SUPPORTED_MODES = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_SUPPORTED_MODES
)
_VIEW_DOCUMENT_DEFAULT_MAX_CHARS = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_DEFAULT_MAX_CHARS
)
_VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS
)
_VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS
)
_VIEW_DOCUMENT_PDF_EXTENSIONS = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_PDF_EXTENSIONS
)
_VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES
)
_VIEW_DOCUMENT_PDF_MIME_TYPES = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_PDF_MIME_TYPES
)
_VIEW_DOCUMENT_TEXT_ENCODINGS = (
    document_tools_view_document_helpers_runtime._VIEW_DOCUMENT_TEXT_ENCODINGS
)
_normalize_view_document_mode = (
    document_tools_view_document_helpers_runtime.normalize_view_document_mode
)
_safe_non_negative_int = document_tools_view_document_helpers_runtime.safe_non_negative_int
_decode_document_text = document_tools_view_document_helpers_runtime.decode_document_text
_document_class = document_tools_view_document_helpers_runtime.document_class
_text_slice_payload = document_tools_view_document_helpers_runtime.text_slice_payload
_view_document_payload_base = (
    document_tools_view_document_helpers_runtime.view_document_payload_base
)
_view_document_failure_payload = (
    document_tools_view_document_helpers_runtime.view_document_failure_payload
)
_view_document_success_payload = (
    document_tools_view_document_helpers_runtime.view_document_success_payload
)


def get_office_tools(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
) -> Any:
    return document_tools_office_runtime.get_office_tools(
        cached_tools=cached_tools,
        load_project_tool_module=load_project_tool_module,
    )


def get_internal_policy_tools(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
) -> Any:
    return document_tools_office_runtime.get_internal_policy_tools(
        cached_tools=cached_tools,
        load_project_tool_module=load_project_tool_module,
    )


def office_skills(
    *,
    office_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_office_runtime.office_skills(
        office_tools_factory=office_tools_factory,
        event_factory=event_factory,
    )


def office_skills_result(
    *,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_skills_call: Callable[[], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_office_runtime.office_skills_result(
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_skills_call=office_skills_call,
    )


def office_run(
    *,
    skill_name: str,
    args: dict[str, Any] | None = None,
    office_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_office_runtime.office_run(
        skill_name=skill_name,
        args=args,
        office_tools_factory=office_tools_factory,
        event_factory=event_factory,
    )


def office_run_result(
    *,
    skill_name: str,
    args: dict[str, Any] | None = None,
    office_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    office_run_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_office_runtime.office_run_result(
        skill_name=skill_name,
        args=args,
        office_tools_factory=office_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        office_run_call=office_run_call,
    )


def view_image(
    *,
    path: str,
    detail: str | None = None,
    image_input_capable: bool = True,
    workspace_root_factory: Callable[[], Path],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_media_runtime.view_image(
        path=path,
        detail=detail,
        image_input_capable=image_input_capable,
        workspace_root_factory=workspace_root_factory,
        event_factory=event_factory,
    )


def view_image_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_image_call: Callable[[str], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_media_runtime.view_image_result(
        path=path,
        result_from_event=result_from_event,
        view_image_call=view_image_call,
    )


def view_document(
    *,
    path: str,
    workspace_root_factory: Callable[[], Path],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    mode: str = "auto",
    max_chars: int = _VIEW_DOCUMENT_DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> ToolEvent:
    return document_tools_media_runtime.view_document(
        path=path,
        workspace_root_factory=workspace_root_factory,
        event_factory=event_factory,
        mode=mode,
        max_chars=max_chars,
        offset=offset,
    )


def view_document_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_document_call: Callable[..., ToolEvent],
    mode: str = "auto",
    max_chars: int = _VIEW_DOCUMENT_DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> CommandExecutionResult:
    return document_tools_media_runtime.view_document_result(
        path=path,
        result_from_event=result_from_event,
        view_document_call=view_document_call,
        mode=mode,
        max_chars=max_chars,
        offset=offset,
    )


def policy_doc_import(
    *,
    path: str,
    library_root: str | None = None,
    recursive: bool = True,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_policy_runtime.policy_doc_import(
        path=path,
        library_root=library_root,
        recursive=recursive,
        internal_policy_tools_factory=internal_policy_tools_factory,
        event_factory=event_factory,
    )


def policy_doc_list(
    *,
    library_root: str | None = None,
    limit: int = 50,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_policy_runtime.policy_doc_list(
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        event_factory=event_factory,
    )


def policy_doc_search(
    *,
    query: str,
    library_root: str | None = None,
    limit: int = 10,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_policy_runtime.policy_doc_search(
        query=query,
        library_root=library_root,
        limit=limit,
        internal_policy_tools_factory=internal_policy_tools_factory,
        event_factory=event_factory,
    )


def policy_doc_read(
    *,
    doc_id: str | None = None,
    path: str | None = None,
    library_root: str | None = None,
    max_chars: int = 12000,
    internal_policy_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return document_tools_policy_runtime.policy_doc_read(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=internal_policy_tools_factory,
        event_factory=event_factory,
    )


def policy_doc_import_result(
    *,
    path: str,
    library_root: str | None = None,
    recursive: bool = True,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_import_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_policy_runtime.policy_doc_import_result(
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
    library_root: str | None = None,
    limit: int = 50,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_list_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_policy_runtime.policy_doc_list_result(
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
    library_root: str | None = None,
    limit: int = 10,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_policy_runtime.policy_doc_search_result(
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
    doc_id: str | None = None,
    path: str | None = None,
    library_root: str | None = None,
    max_chars: int = 12000,
    internal_policy_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    policy_doc_read_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return document_tools_policy_runtime.policy_doc_read_result(
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
        internal_policy_tools_factory=internal_policy_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        policy_doc_read_call=policy_doc_read_call,
    )
