from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.media_file_types import SUPPORTED_IMAGE_MIME_BY_EXTENSION
from cli.agent_cli.tools_core.document_tools_view_document_normalization_helpers_runtime import (
    _VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS,
    _VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES,
    _VIEW_DOCUMENT_PDF_EXTENSIONS,
    _VIEW_DOCUMENT_PDF_MIME_TYPES,
    _VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS,
    _VIEW_DOCUMENT_TEXT_ENCODINGS,
)


def decode_document_text(data: bytes) -> tuple[str | None, str]:
    for encoding in _VIEW_DOCUMENT_TEXT_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, ""


def document_class(*, path: Path, mime_type: str) -> str:
    # Extraction-time subtype used only after the probe layer has already classified the source as document/image/binary.
    suffix = path.suffix.lower()
    normalized_mime = str(mime_type or "").strip().lower()
    if suffix in _VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS or normalized_mime == "application/json":
        return "structured_json"
    if suffix in _VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS or normalized_mime in _VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES:
        return "notebook"
    if suffix in _VIEW_DOCUMENT_PDF_EXTENSIONS or normalized_mime in _VIEW_DOCUMENT_PDF_MIME_TYPES:
        return "pdf"
    if suffix in SUPPORTED_IMAGE_MIME_BY_EXTENSION or normalized_mime.startswith("image/"):
        return "image"
    return "unknown"


def text_slice_payload(
    text: str,
    *,
    encoding: str,
    offset: int,
    max_chars: int,
) -> dict[str, Any]:
    begin = max(0, min(len(text), offset))
    end = min(len(text), begin + max_chars)
    chunk = text[begin:end]
    return {
        "text": chunk,
        "encoding": encoding,
        "offset": begin,
        "max_chars": max_chars,
        "returned_chars": len(chunk),
        "total_chars": len(text),
        "truncated": end < len(text),
        "line_count": chunk.count("\n") + (1 if chunk else 0),
    }


__all__ = [
    "decode_document_text",
    "document_class",
    "text_slice_payload",
]
