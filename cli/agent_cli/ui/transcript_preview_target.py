from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+")
_SPACE_TOKEN_RE = re.compile(r"\S+")
_LEADING_STRIP = "`'\"([<{"
_TRAILING_STRIP = "`'\".,;!?)]>}"


@dataclass(frozen=True)
class PreviewTarget:
    kind: str
    value: str
    line_number: int | None = None


@dataclass(frozen=True)
class PreviewTargetSpan:
    start: int
    end: int
    target: PreviewTarget


def target_at_line_column(
    line: str,
    column: int,
    *,
    workspace_roots: Sequence[str | Path] | None = None,
) -> PreviewTarget | None:
    span = target_span_at_line_column(line, column, workspace_roots=workspace_roots)
    return span.target if span is not None else None


def target_span_at_line_column(
    line: str,
    column: int,
    *,
    workspace_roots: Sequence[str | Path] | None = None,
) -> PreviewTargetSpan | None:
    text = str(line or "")
    if not text:
        return None
    safe_column = max(0, int(column))
    for match in _URL_RE.finditer(text):
        start, end, token = _strip_token_span(text, match.start(), match.end())
        if _column_in_span(safe_column, start, end):
            return PreviewTargetSpan(
                start=start,
                end=end,
                target=PreviewTarget(kind="url", value=token),
            )
    for match in _SPACE_TOKEN_RE.finditer(text):
        start, end, token = _strip_token_span(text, match.start(), match.end())
        if not _column_in_span(safe_column, start, end):
            continue
        target = _file_target_from_token(token, workspace_roots=workspace_roots)
        if target is not None:
            return PreviewTargetSpan(start=start, end=end, target=target)
    return None


def target_for_area_location(area: Any, location: tuple[int, int]) -> PreviewTarget | None:
    span = target_span_for_area_location(area, location)
    return span.target if span is not None else None


def target_span_for_area_location(area: Any, location: tuple[int, int]) -> PreviewTargetSpan | None:
    row, column = location
    line = _area_line(area, row)
    if line is None:
        return None
    return target_span_at_line_column(line, column, workspace_roots=_workspace_roots())


def update_hover_target_for_area(area: Any, location: tuple[int, int] | None) -> None:
    span_value: tuple[int, int, int] | None = None
    if location is not None:
        row, _column = location
        target_span = target_span_for_area_location(area, location)
        if target_span is not None and target_span.end > target_span.start:
            span_value = (int(row), target_span.start, target_span.end)
    _set_hover_span(area, span_value)


def clear_hover_target(area: Any) -> None:
    _set_hover_span(area, None)


def _column_in_span(column: int, start: int, end: int) -> bool:
    return start <= column < end or (column == end and end > start)


def _strip_token_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start] in _LEADING_STRIP:
        start += 1
    while end > start and text[end - 1] in _TRAILING_STRIP:
        end -= 1
    return start, end, text[start:end]


def _file_target_from_token(
    token: str,
    *,
    workspace_roots: Sequence[str | Path] | None,
) -> PreviewTarget | None:
    if not token or token.startswith(("http://", "https://")):
        return None
    path_text, line_number = _split_path_line(token)
    if not path_text:
        return None
    resolved = _resolve_existing_path(path_text, workspace_roots=workspace_roots)
    if resolved is None:
        return None
    if resolved.is_dir():
        return PreviewTarget(kind="dir", value=str(resolved), line_number=None)
    return PreviewTarget(kind="file", value=str(resolved), line_number=line_number)


def _split_path_line(token: str) -> tuple[str, int | None]:
    match = re.match(r"^(?P<path>.+?):(?P<line>\d+)$", token)
    if not match:
        return token, None
    path_text = str(match.group("path") or "")
    try:
        line_number = int(match.group("line"))
    except ValueError:
        line_number = None
    if line_number is not None and line_number <= 0:
        line_number = None
    return path_text, line_number


def _resolve_existing_path(
    path_text: str,
    *,
    workspace_roots: Sequence[str | Path] | None,
) -> Path | None:
    candidate = Path(path_text).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for root in workspace_roots or _workspace_roots():
        root_path = Path(root).expanduser()
        resolved = (root_path / candidate).resolve()
        if resolved.exists():
            return resolved
    return None


def _workspace_roots() -> tuple[Path, ...]:
    import os

    roots: list[Path] = []
    for value in (
        os.environ.get("AGENTHUB_PREVIEW_WORKSPACE"),
        os.environ.get("AGENTHUB_STARTUP_CWD"),
        os.getcwd(),
    ):
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve()
        except Exception:
            continue
        if path not in roots:
            roots.append(path)
    return tuple(roots)


def _area_line(area: Any, row: int) -> str | None:
    try:
        return str(area.document[int(row)])
    except Exception:
        pass
    try:
        lines = str(getattr(area, "text", "")).splitlines()
        return lines[int(row)]
    except Exception:
        return None


def _set_hover_span(area: Any, span: tuple[int, int, int] | None) -> None:
    current = getattr(area, "_preview_hover_target_span", None)
    if current == span:
        return
    area._preview_hover_target_span = span
    try:
        area.refresh(repaint=True)
    except TypeError:
        try:
            area.refresh()
        except Exception:
            pass
    except Exception:
        pass
