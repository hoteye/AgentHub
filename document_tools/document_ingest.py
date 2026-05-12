#!/usr/bin/env python3
"""
附件文档解析。

支持：
- zip/7z 解压
- doc/docx/pdf 解析
- xls/xlsx 解析
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from document_tools.document_ingest_file_helpers import (
    _truncate,
    convert_legacy_office,
    extract_7z_safe,
    extract_zip_safe,
)
from document_tools.document_ingest_render_helpers import (
    _build_merge_metadata,
    _write_json_artifact,
    _write_markdown_artifact,
    render_markdown,
    summarize_document_content,
)

SUPPORTED_SUFFIXES = {".zip", ".7z", ".doc", ".docx", ".pdf", ".xls", ".xlsx"}
PARSEABLE_SUFFIXES = {".doc", ".docx", ".pdf", ".xls", ".xlsx"}


def parse_docx(path: Path) -> Dict:
    from document_tools.document_ingest_parser_helpers import parse_docx as _parse_docx

    return _parse_docx(path)


def parse_xlsx(path: Path) -> Dict:
    from document_tools.document_ingest_parser_helpers import parse_xlsx as _parse_xlsx

    return _parse_xlsx(path)


def parse_xls(path: Path) -> Dict:
    from document_tools.document_ingest_parser_helpers import parse_xls as _parse_xls

    return _parse_xls(path)


def parse_pdf(path: Path) -> Dict:
    from document_tools.document_ingest_parser_helpers import parse_pdf as _parse_pdf

    return _parse_pdf(path)


def _flatten_parseable_files(
    paths: Sequence[Path],
    extract_root: Path,
    convert_root: Path,
    errors: Optional[List[Dict]] = None,
) -> List[Path]:
    resolved: List[Path] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".zip":
            extracted = extract_zip_safe(path, extract_root)
            resolved.extend(_flatten_parseable_files(extracted, extract_root, convert_root, errors=errors))
            continue
        if suffix == ".7z":
            try:
                extracted = extract_7z_safe(path, extract_root)
            except Exception as exc:
                if errors is not None:
                    errors.append({"path": str(path), "stage": "extract", "error": str(exc)})
                continue
            resolved.extend(_flatten_parseable_files(extracted, extract_root, convert_root, errors=errors))
            continue
        if suffix not in PARSEABLE_SUFFIXES:
            continue
        if suffix == ".doc":
            try:
                resolved.append(convert_legacy_office(path, convert_root))
            except Exception as exc:
                if errors is not None:
                    errors.append({"path": str(path), "stage": "convert", "error": str(exc)})
            continue
        resolved.append(path)
    return resolved


def ingest_document(path: Path, runtime_root: Optional[Path] = None) -> Dict:
    path = Path(path)
    runtime_root = runtime_root or (path.parent / ".document_ingest")
    extract_root = runtime_root / "extracted"
    convert_root = runtime_root / "converted"
    markdown_root = runtime_root / "markdown"
    merge_metadata_root = runtime_root / "merge_metadata"
    extract_root.mkdir(parents=True, exist_ok=True)
    convert_root.mkdir(parents=True, exist_ok=True)
    markdown_root.mkdir(parents=True, exist_ok=True)
    merge_metadata_root.mkdir(parents=True, exist_ok=True)

    errors: List[Dict] = []
    parse_targets = _flatten_parseable_files(
        [path],
        extract_root=extract_root,
        convert_root=convert_root,
        errors=errors,
    )
    documents = []
    for target in parse_targets:
        suffix = target.suffix.lower()
        try:
            if suffix == ".docx":
                file_type = "docx"
                content = parse_docx(target)
                title = str(content.get("title") or target.stem)
            elif suffix == ".xlsx":
                file_type = "xlsx"
                content = parse_xlsx(target)
                title = target.stem
            elif suffix == ".xls":
                file_type = "xls"
                content = parse_xls(target)
                title = target.stem
            elif suffix == ".pdf":
                file_type = "pdf"
                content = parse_pdf(target)
                title = str(content.get("title") or target.stem)
            else:
                continue
            markdown_text = render_markdown(file_type, content, title=title)
            markdown_path = _write_markdown_artifact(markdown_root, target.name, markdown_text)
            merge_metadata_path = None
            if file_type in {"xlsx", "xls"}:
                merge_metadata_path = _write_json_artifact(
                    merge_metadata_root,
                    target.name,
                    _build_merge_metadata(file_type, content, source_name=target.name),
                    suffix=".merge_metadata.json",
                )
            documents.append(
                {
                    "path": str(target),
                    "name": target.name,
                    "file_type": file_type,
                    "content": content,
                    "content_summary": summarize_document_content(file_type, content),
                    "markdown_path": markdown_path,
                    "markdown_preview": _truncate(markdown_text, 2000),
                    "merge_metadata_path": merge_metadata_path,
                }
            )
        except Exception as exc:
            errors.append({"path": str(target), "stage": "parse", "error": str(exc)})

    return {
        "source_path": str(path),
        "source_name": path.name,
        "source_suffix": path.suffix.lower(),
        "resolved_document_count": len(documents),
        "documents": documents,
        "errors": errors,
    }


def ingest_documents(paths: Sequence[Path], runtime_root: Path) -> List[Dict]:
    result = []
    for path in paths:
        result.append(ingest_document(Path(path), runtime_root=runtime_root))
    return result


def dumps_json(data: Dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
