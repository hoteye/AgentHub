from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List

from . import file_read_runtime_helpers_io

_FILE_READ_DEFAULT_OFFSET = 1
_FILE_READ_DEFAULT_LIMIT = 2000
_FILE_READ_MAX_LINE_LENGTH = 500
_TAB_WIDTH = 4
_COMMENT_PREFIXES = ("#", "//", "--")


def format_file_read_line(line_number: int, raw_line: str) -> str:
    text = str(raw_line or "")
    if len(text) > _FILE_READ_MAX_LINE_LENGTH:
        text = text[:_FILE_READ_MAX_LINE_LENGTH]
    return f"L{int(line_number)}: {text}"


class LineRecord:
    def __init__(self, *, number: int, raw: str) -> None:
        self.number = int(number)
        self.raw = str(raw or "")
        self.display = self.raw[:_FILE_READ_MAX_LINE_LENGTH]
        self.indent = measure_indent(self.raw)

    def trimmed(self) -> str:
        return self.raw.lstrip()

    def is_blank(self) -> bool:
        return not self.trimmed()

    def is_comment(self) -> bool:
        text = self.raw.strip()
        return any(text.startswith(prefix) for prefix in _COMMENT_PREFIXES)


def build_file_read_payload(
    *,
    root: Path,
    target: Path,
    offset: int | None,
    limit: int | None,
    max_chars: int | None,
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> Dict[str, Any]:
    raw_text = target.read_text(encoding="utf-8", errors="replace")
    all_lines = raw_text.splitlines()
    total_line_count = len(all_lines)
    use_line_slice = offset is not None or limit is not None or max_chars is None

    if use_line_slice:
        resolved_offset = int(offset or _FILE_READ_DEFAULT_OFFSET)
        resolved_limit = int(limit or _FILE_READ_DEFAULT_LIMIT)
        selected, truncated = slice_text_lines(
            all_lines,
            offset=resolved_offset,
            limit=resolved_limit,
            file_tool_error_cls=file_tool_error_cls,
        )
        rendered = "\n".join(format_file_read_line(item["line"], item["text"]) for item in selected)
        return {
            "ok": True,
            "workspace_root": str(root),
            "path": relative_text_fn(target, root),
            "char_count": len(raw_text),
            "line_count": total_line_count,
            "returned_line_count": len(selected),
            "offset": resolved_offset,
            "limit": resolved_limit,
            "truncated": truncated,
            "mode": "slice",
            "text": rendered,
            "excerpt_lines": selected[:8],
        }

    limited = max(1, int(max_chars or 12000))
    rendered = raw_text[:limited]
    return {
        "ok": True,
        "workspace_root": str(root),
        "path": relative_text_fn(target, root),
        "char_count": len(raw_text),
        "line_count": total_line_count,
        "truncated": len(raw_text) > limited,
        "mode": "chars",
        "max_chars": limited,
        "text": rendered,
        "excerpt_lines": excerpt_nonblank_lines(all_lines),
    }


def build_read_file_payload(
    *,
    root: Path,
    target: Path,
    offset: int | None,
    limit: int | None,
    mode_text: str,
    indentation: Dict[str, Any] | None,
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> Dict[str, Any]:
    records = read_line_records(target, file_tool_error_cls=file_tool_error_cls)
    total_line_count = len(records)
    resolved_offset = int(offset or _FILE_READ_DEFAULT_OFFSET)
    resolved_limit = int(limit or _FILE_READ_DEFAULT_LIMIT)

    if mode_text == "indentation":
        selected = indentation_mode_records(
            records,
            offset=resolved_offset,
            limit=resolved_limit,
            indentation=indentation,
            file_tool_error_cls=file_tool_error_cls,
        )
        truncated = len(selected) < total_line_count
    else:
        selected, truncated = slice_line_records(
            records,
            offset=resolved_offset,
            limit=resolved_limit,
            file_tool_error_cls=file_tool_error_cls,
        )

    relative_path = relative_text_fn(target, root)
    payload = {
        "ok": True,
        "workspace_root": str(root),
        "file_path": relative_path,
        "path": relative_path,
        "line_count": total_line_count,
        "returned_line_count": len(selected),
        "offset": resolved_offset,
        "limit": resolved_limit,
        "truncated": truncated,
        "mode": mode_text,
        "text": "\n".join(format_file_read_line(record.number, record.display) for record in selected),
        "excerpt_lines": file_records_excerpt(selected),
    }
    if mode_text == "indentation":
        payload["indentation"] = normalized_indentation_options(indentation=indentation, offset=resolved_offset)
    return payload


def slice_text_lines(
    all_lines: List[str],
    *,
    offset: int,
    limit: int,
    file_tool_error_cls: type[Exception],
) -> tuple[List[Dict[str, Any]], bool]:
    total_line_count = len(all_lines)
    validate_window(offset=offset, limit=limit, total_line_count=total_line_count, file_tool_error_cls=file_tool_error_cls)
    end_index = min(total_line_count, offset - 1 + limit)
    selected = []
    for line_number in range(offset, end_index + 1):
        raw_line = all_lines[line_number - 1]
        selected.append({"line": line_number, "text": raw_line[:_FILE_READ_MAX_LINE_LENGTH]})
    return selected, end_index < total_line_count


def excerpt_nonblank_lines(all_lines: List[str], *, limit: int = 8) -> List[Dict[str, Any]]:
    excerpt_lines: List[Dict[str, Any]] = []
    for line_number, raw_line in enumerate(all_lines, start=1):
        if not raw_line.strip():
            continue
        excerpt_lines.append({"line": line_number, "text": raw_line[:400]})
        if len(excerpt_lines) >= limit:
            break
    return excerpt_lines


def normalized_indentation_options(*, indentation: Dict[str, Any] | None, offset: int) -> Dict[str, Any]:
    return {
        "anchor_line": int((indentation or {}).get("anchor_line") or offset),
        "max_levels": int((indentation or {}).get("max_levels") or 0),
        "include_siblings": bool((indentation or {}).get("include_siblings", False)),
        "include_header": bool((indentation or {}).get("include_header", True)),
        "max_lines": (
            int((indentation or {}).get("max_lines"))
            if (indentation or {}).get("max_lines") is not None
            else None
        ),
    }


def decode_line(raw_bytes: bytes) -> str:
    raw = bytes(raw_bytes or b"")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    return raw.decode("utf-8", errors="replace")


def read_line_records(target: Path, *, file_tool_error_cls: type[Exception]) -> List[LineRecord]:
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise file_tool_error_cls(f"failed to read file: {exc}") from exc
    records: List[LineRecord] = []
    for index, raw_line in enumerate(raw.splitlines(keepends=True), start=1):
        records.append(LineRecord(number=index, raw=decode_line(raw_line)))
    if raw and not raw.endswith((b"\n", b"\r")):
        return records
    if not raw:
        return []
    return records


def trim_empty_line_records(records: deque[LineRecord]) -> None:
    while records and records[0].is_blank():
        records.popleft()
    while records and records[-1].is_blank():
        records.pop()


def measure_indent(line: str) -> int:
    indent = 0
    for char in str(line or ""):
        if char == " ":
            indent += 1
        elif char == "\t":
            indent += _TAB_WIDTH
        else:
            break
    return indent


def effective_indents(records: List[LineRecord]) -> List[int]:
    effective: List[int] = []
    previous_indent = 0
    for record in records:
        if record.is_blank():
            effective.append(previous_indent)
            continue
        previous_indent = record.indent
        effective.append(previous_indent)
    return effective


def validate_window(
    *,
    offset: int,
    limit: int,
    total_line_count: int,
    file_tool_error_cls: type[Exception],
) -> None:
    if offset <= 0:
        raise file_tool_error_cls("offset must be a 1-indexed line number")
    if limit <= 0:
        raise file_tool_error_cls("limit must be greater than zero")
    if offset > total_line_count:
        raise file_tool_error_cls("offset exceeds file length")


def slice_line_records(
    records: List[LineRecord],
    *,
    offset: int,
    limit: int,
    file_tool_error_cls: type[Exception],
) -> tuple[List[LineRecord], bool]:
    total_line_count = len(records)
    validate_window(offset=offset, limit=limit, total_line_count=total_line_count, file_tool_error_cls=file_tool_error_cls)
    end_index = min(total_line_count, offset - 1 + limit)
    return records[offset - 1 : end_index], end_index < total_line_count


def indentation_mode_records(
    records: List[LineRecord],
    *,
    offset: int,
    limit: int,
    indentation: Dict[str, Any] | None,
    file_tool_error_cls: type[Exception],
) -> List[LineRecord]:
    return file_read_runtime_helpers_io.indentation_mode_records_impl(
        records,
        offset=offset,
        limit=limit,
        indentation=indentation,
        file_tool_error_cls=file_tool_error_cls,
        effective_indents_fn=effective_indents,
        trim_empty_line_records_fn=trim_empty_line_records,
        tab_width=_TAB_WIDTH,
    )


def file_records_excerpt(records: List[LineRecord], *, limit: int = 8) -> List[Dict[str, Any]]:
    return [
        {
            "line": record.number,
            "text": record.display,
        }
        for record in records[:limit]
    ]
