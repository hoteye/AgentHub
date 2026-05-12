from __future__ import annotations

import json
from typing import Any, Callable, Dict

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core.document_tools_view_document_normalization_helpers_runtime import (
    _VIEW_DOCUMENT_SUPPORTED_MODES,
)


_UNSUPPORTED_BASELINE_MESSAGES = {
    "pdf": (
        "PDF documents are outside the TASK A baseline. "
        "view_document currently supports text-like files and structured JSON only."
    ),
    "notebook": (
        "Notebook documents are outside the TASK A baseline. "
        "view_document currently supports text-like files and structured JSON only."
    ),
}


def view_document_payload_base(
    *,
    ok: bool,
    requested_path: str,
    path: str,
    document_class: str,
    extraction_state: str,
    mode: str,
    media_mode: str,
    mime_type: str,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "requested_path": requested_path,
        "path": path,
        "source_mode": "tool_path",
        "capability_baseline": "extraction_only",
        "document_class": str(document_class or "unknown"),
        "extraction_state": str(extraction_state or ""),
        "mode": mode,
        "media_mode": media_mode,
        "mime_type": mime_type,
        "supported_modes": list(_VIEW_DOCUMENT_SUPPORTED_MODES),
        "text_slice": None,
        "structured_content": None,
    }


def view_document_failure_payload(
    *,
    requested_path: str,
    path: str,
    document_class: str,
    extraction_state: str,
    mode: str,
    media_mode: str,
    mime_type: str,
    error_code: str,
    display_message: str,
    media_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = view_document_payload_base(
        ok=False,
        requested_path=requested_path,
        path=path,
        document_class=document_class,
        extraction_state=extraction_state,
        mode=mode,
        media_mode=media_mode,
        mime_type=mime_type,
    )
    payload["error_code"] = str(error_code or "view_document_failed")
    payload["display_message"] = str(display_message or "Document extraction failed.")
    if media_probe is not None:
        payload["media_probe"] = dict(media_probe)
    return payload


def view_document_success_payload(
    *,
    requested_path: str,
    path: str,
    document_class: str,
    extraction_state: str,
    mode: str,
    media_mode: str,
    mime_type: str,
    text_slice: dict[str, Any] | None = None,
    structured_content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = view_document_payload_base(
        ok=True,
        requested_path=requested_path,
        path=path,
        document_class=document_class,
        extraction_state=extraction_state,
        mode=mode,
        media_mode=media_mode,
        mime_type=mime_type,
    )
    if text_slice is not None:
        payload["text_slice"] = dict(text_slice)
    if structured_content is not None:
        payload["structured_content"] = dict(structured_content)
    payload["error_code"] = ""
    payload["display_message"] = ""
    return payload


def build_unsupported_document_event(
    *,
    requested_path: str,
    resolved_path: str,
    normalized_mode: str,
    document_kind: str,
    mime_type: str,
    probe_result: Any,
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent | None:
    if document_kind == "image":
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=requested_path,
                path=resolved_path,
                document_class=document_kind,
                extraction_state="unsupported_document_class",
                mode=normalized_mode,
                media_mode="unsupported_media",
                mime_type=mime_type,
                error_code="unsupported_media_mode",
                display_message="Image extraction is not supported by view_document. Use view_image(path) instead.",
                media_probe=probe_result.to_dict(),
            ),
        )
    baseline_message = _UNSUPPORTED_BASELINE_MESSAGES.get(document_kind)
    if baseline_message is None:
        return None
    return event_factory(
        "view_document",
        False,
        "view document failed",
        view_document_failure_payload(
            requested_path=requested_path,
            path=resolved_path,
            document_class=document_kind,
            extraction_state="unsupported_document_class",
            mode=normalized_mode,
            media_mode="unsupported_media",
            mime_type=mime_type,
            error_code="unsupported_document_type",
            display_message=baseline_message,
        ),
    )


def build_structured_document_event(
    *,
    requested_path: str,
    resolved_path: str,
    resolved_name: str,
    document_kind: str,
    normalized_mode: str,
    mime_type: str,
    text: str,
    encoding: str,
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent | None:
    if normalized_mode not in {"auto", "structured_content"} or document_kind != "structured_json":
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        if normalized_mode != "structured_content":
            return None
        return event_factory(
            "view_document",
            False,
            "view document failed",
            view_document_failure_payload(
                requested_path=requested_path,
                path=resolved_path,
                document_class=document_kind,
                extraction_state="extraction_failed",
                mode=normalized_mode,
                media_mode="structured_content",
                mime_type=mime_type,
                error_code="structured_parse_failed",
                display_message=f"Failed to parse structured document content: {exc}",
            ),
        )
    structured_payload = {
        "format": "json",
        "encoding": encoding,
        "char_count": len(text),
        "top_level_type": type(parsed).__name__,
        "data": parsed,
    }
    payload = view_document_success_payload(
        requested_path=requested_path,
        path=resolved_path,
        document_class=document_kind,
        extraction_state="structured_content_ready",
        mode=normalized_mode,
        media_mode="structured_content",
        mime_type=mime_type,
        structured_content=structured_payload,
    )
    return event_factory(
        "view_document",
        True,
        f"document structured content ready: {resolved_name}",
        payload,
    )


__all__ = [
    "build_structured_document_event",
    "build_unsupported_document_event",
    "view_document_failure_payload",
    "view_document_payload_base",
    "view_document_success_payload",
]
