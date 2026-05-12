"""Document ingest and markdown helpers for the Office worker."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from shared.document_tools.document_ingest import ingest_document


def _document_markdown_result(path: str, *, runtime_root: Optional[str] = None, expected_type: Optional[str] = None) -> Dict[str, Any]:
    result = ingest_document(Path(path), runtime_root=Path(runtime_root) if runtime_root else None)
    documents = result.get("documents") or []
    target = None
    if expected_type is None:
        target = documents[0] if documents else None
    else:
        target = next((doc for doc in documents if doc.get("file_type") == expected_type), None)
    if target is None:
        return {
            "ok": False,
            "path": str(Path(path).resolve()),
            "errors": result.get("errors", []),
            "reason": "document_not_parsed",
        }
    return {
        "ok": True,
        "path": str(Path(path).resolve()),
        "file_type": target.get("file_type"),
        "name": target.get("name"),
        "content_summary": target.get("content_summary"),
        "markdown_path": target.get("markdown_path"),
        "markdown_preview": target.get("markdown_preview"),
        "merge_metadata_path": target.get("merge_metadata_path"),
        "errors": result.get("errors", []),
    }


def _read_docx_markdown(path: str, *, runtime_root: Optional[str] = None) -> Dict[str, Any]:
    result = _document_markdown_result(path, runtime_root=runtime_root, expected_type="docx")
    result["skill"] = "read_docx_markdown"
    return result


def _read_pdf_markdown(path: str, *, runtime_root: Optional[str] = None) -> Dict[str, Any]:
    result = _document_markdown_result(path, runtime_root=runtime_root, expected_type="pdf")
    result["skill"] = "read_pdf_markdown"
    return result


def _ingest_office_file(path: str, *, runtime_root: Optional[str] = None) -> Dict[str, Any]:
    result = ingest_document(Path(path), runtime_root=Path(runtime_root) if runtime_root else None)
    return {
        "ok": True,
        "skill": "ingest_office_file",
        **result,
    }
