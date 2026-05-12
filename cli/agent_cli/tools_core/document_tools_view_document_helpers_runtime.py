from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import (
    document_tools_view_document_normalization_helpers_runtime,
    document_tools_view_document_projection_helpers_runtime,
    document_tools_view_document_pure_helpers_runtime,
)
from cli.agent_cli.tools_core.media_ingest_runtime import probe_local_media_path


ViewDocumentRequest = document_tools_view_document_normalization_helpers_runtime.ViewDocumentRequest
_VIEW_DOCUMENT_SUPPORTED_MODES = document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_SUPPORTED_MODES
_VIEW_DOCUMENT_DEFAULT_MAX_CHARS = (
    document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_DEFAULT_MAX_CHARS
)
_VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS = (
    document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS
)
_VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS = (
    document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS
)
_VIEW_DOCUMENT_PDF_EXTENSIONS = document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_PDF_EXTENSIONS
_VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES = (
    document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES
)
_VIEW_DOCUMENT_PDF_MIME_TYPES = (
    document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_PDF_MIME_TYPES
)
_VIEW_DOCUMENT_TEXT_ENCODINGS = document_tools_view_document_normalization_helpers_runtime._VIEW_DOCUMENT_TEXT_ENCODINGS
normalize_view_document_mode = (
    document_tools_view_document_normalization_helpers_runtime.normalize_view_document_mode
)
safe_non_negative_int = document_tools_view_document_normalization_helpers_runtime.safe_non_negative_int
normalize_view_document_request = (
    document_tools_view_document_normalization_helpers_runtime.normalize_view_document_request
)
decode_document_text = document_tools_view_document_pure_helpers_runtime.decode_document_text
document_class = document_tools_view_document_pure_helpers_runtime.document_class
text_slice_payload = document_tools_view_document_pure_helpers_runtime.text_slice_payload
view_document_payload_base = (
    document_tools_view_document_projection_helpers_runtime.view_document_payload_base
)
view_document_failure_payload = (
    document_tools_view_document_projection_helpers_runtime.view_document_failure_payload
)
view_document_success_payload = (
    document_tools_view_document_projection_helpers_runtime.view_document_success_payload
)
_build_unsupported_document_event = (
    document_tools_view_document_projection_helpers_runtime.build_unsupported_document_event
)
_build_structured_document_event = (
    document_tools_view_document_projection_helpers_runtime.build_structured_document_event
)


def build_view_document_event(
    *,
    path: str,
    workspace_root_factory: Callable[[], Path],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
    mode: str = "auto",
    max_chars: int = _VIEW_DOCUMENT_DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> ToolEvent:
    request = normalize_view_document_request(path=path, mode=mode, max_chars=max_chars, offset=offset)
    workspace_root = workspace_root_factory()
    if not request.requested_path:
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path="",
                document_class="unknown",
                extraction_state="extraction_failed",
                mode=request.normalized_mode if request.normalized_mode != "invalid" else str(mode or ""),
                media_mode="unsupported_media",
                mime_type="",
                error_code="invalid_path",
                display_message="Document path is required.",
            ),
        )
    if request.normalized_mode == "invalid":
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path="",
                document_class="unknown",
                extraction_state="extraction_failed",
                mode=str(mode or ""),
                media_mode="unsupported_media",
                mime_type="",
                error_code="invalid_mode",
                display_message="Unsupported extraction mode. Use auto, text_slice, or structured_content.",
            ),
        )

    probe_result = probe_local_media_path(request.requested_path, workspace_root=workspace_root)
    source = probe_result.source
    if not probe_result.ok or source is None:
        error_code = (
            "invalid_path" if str(probe_result.error_code or "").strip() == "invalid_path" else "unreadable_document"
        )
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path=str(getattr(source, "path", "") or ""),
                document_class="unknown",
                extraction_state="extraction_failed",
                mode=request.normalized_mode,
                media_mode="unsupported_media",
                mime_type=str(getattr(source, "mime_type", "") or ""),
                error_code=error_code,
                display_message=str(probe_result.display_message or "Document path probe failed."),
            ),
        )

    resolved = Path(source.path)
    resolved_path_text = source.path
    mime_type = source.mime_type
    document_kind = document_class(path=resolved, mime_type=mime_type)

    unsupported_event = _build_unsupported_document_event(
        requested_path=request.requested_path,
        resolved_path=resolved_path_text,
        normalized_mode=request.normalized_mode,
        document_kind=document_kind,
        mime_type=mime_type,
        probe_result=probe_result,
        event_factory=event_factory,
    )
    if unsupported_event is not None:
        return unsupported_event

    try:
        data = resolved.read_bytes()
    except OSError as exc:
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path=resolved_path_text,
                document_class=document_kind,
                extraction_state="extraction_failed",
                mode=request.normalized_mode,
                media_mode="unsupported_media",
                mime_type=mime_type,
                error_code="unreadable_document",
                display_message=f"Document file is not readable: {exc}",
            ),
        )

    text, encoding = decode_document_text(data)
    if text is None:
        resolved_document_class = "binary" if document_kind == "unknown" else document_kind
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path=resolved_path_text,
                document_class=resolved_document_class,
                extraction_state="unsupported_document_class",
                mode=request.normalized_mode,
                media_mode="unsupported_media",
                mime_type=mime_type,
                error_code="unsupported_media_mode",
                display_message="Binary document extraction is not supported by view_document.",
            ),
        )
    if document_kind == "unknown":
        document_kind = "text_like"

    structured_event = _build_structured_document_event(
        requested_path=request.requested_path,
        resolved_path=resolved_path_text,
        resolved_name=resolved.name,
        document_kind=document_kind,
        normalized_mode=request.normalized_mode,
        mime_type=mime_type,
        text=text,
        encoding=encoding,
        event_factory=event_factory,
    )
    if structured_event is not None:
        return structured_event

    if request.normalized_mode == "structured_content":
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=request.requested_path,
                path=resolved_path_text,
                document_class=document_kind,
                extraction_state="unsupported_document_class",
                mode=request.normalized_mode,
                media_mode="unsupported_media",
                mime_type=mime_type,
                error_code="unsupported_media_mode",
                display_message="Structured extraction currently supports JSON documents only.",
            ),
        )

    text_slice = text_slice_payload(
        text,
        encoding=encoding,
        offset=request.offset,
        max_chars=request.max_chars,
    )
    payload = view_document_success_payload(
        requested_path=request.requested_path,
        path=resolved_path_text,
        document_class=document_kind,
        extraction_state="text_slice_ready",
        mode=request.normalized_mode,
        media_mode="text_slice",
        mime_type=mime_type,
        text_slice=text_slice,
    )
    return event_factory(
        "view_document",
        True,
        f"document text slice ready: {resolved.name}",
        payload,
    )

