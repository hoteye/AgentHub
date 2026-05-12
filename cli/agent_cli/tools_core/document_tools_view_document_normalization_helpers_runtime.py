from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_VIEW_DOCUMENT_SUPPORTED_MODES = ("text_slice", "structured_content")
_VIEW_DOCUMENT_DEFAULT_MAX_CHARS = 12_000
_VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS = {".json"}
_VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS = {".ipynb"}
_VIEW_DOCUMENT_PDF_EXTENSIONS = {".pdf"}
_VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES = {"application/x-ipynb+json"}
_VIEW_DOCUMENT_PDF_MIME_TYPES = {"application/pdf"}
_VIEW_DOCUMENT_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be")


@dataclass(frozen=True)
class ViewDocumentRequest:
    requested_path: str
    normalized_mode: str
    max_chars: int
    offset: int


def normalize_view_document_mode(mode: str) -> str:
    normalized = str(mode or "auto").strip().lower()
    if normalized not in {"auto", "text_slice", "structured_content"}:
        return "invalid"
    return normalized


def safe_non_negative_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else 0


def normalize_view_document_request(
    *,
    path: str,
    mode: str,
    max_chars: int,
    offset: int,
) -> ViewDocumentRequest:
    return ViewDocumentRequest(
        requested_path=str(path or "").strip(),
        normalized_mode=normalize_view_document_mode(mode),
        max_chars=safe_non_negative_int(max_chars, default=_VIEW_DOCUMENT_DEFAULT_MAX_CHARS),
        offset=safe_non_negative_int(offset, default=0),
    )


__all__ = [
    "ViewDocumentRequest",
    "_VIEW_DOCUMENT_DEFAULT_MAX_CHARS",
    "_VIEW_DOCUMENT_NOTEBOOK_EXTENSIONS",
    "_VIEW_DOCUMENT_NOTEBOOK_MIME_TYPES",
    "_VIEW_DOCUMENT_PDF_EXTENSIONS",
    "_VIEW_DOCUMENT_PDF_MIME_TYPES",
    "_VIEW_DOCUMENT_STRUCTURED_JSON_EXTENSIONS",
    "_VIEW_DOCUMENT_SUPPORTED_MODES",
    "_VIEW_DOCUMENT_TEXT_ENCODINGS",
    "normalize_view_document_mode",
    "normalize_view_document_request",
    "safe_non_negative_int",
]
