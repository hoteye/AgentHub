from __future__ import annotations

from pathlib import Path


def active_prefixed_token(
    text: str,
    cursor_pos: int,
    prefix: str,
    *,
    allow_empty: bool,
) -> tuple[str, int, int] | None:
    if not text:
        return None
    cursor = max(0, min(int(cursor_pos), len(text)))
    if cursor < len(text) and not text[cursor].isspace():
        anchor = cursor
    elif cursor > 0 and not text[cursor - 1].isspace():
        anchor = cursor - 1
    else:
        return None
    start = anchor
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    end = anchor + 1
    while end < len(text) and not text[end].isspace():
        end += 1
    token = text[start:end]
    if not token.startswith(prefix):
        return None
    body = token[len(prefix) :]
    if not allow_empty and not body:
        return None
    return (body, start, end)


def file_query(
    text: str,
    cursor_pos: int,
    *,
    windows_drive_re,
    windows_unc_re,
) -> str | None:
    token = active_prefixed_token(text, cursor_pos, "@", allow_empty=True)
    if token is None:
        return None
    value = token[0].strip()
    if value.startswith(('"', "'")):
        return None
    if windows_drive_re.match(value) or windows_unc_re.match(value):
        return None
    return value


def file_reference_matches(
    workspace_files: list[str],
    query: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    normalized_query = str(query or "").strip().lower().replace("\\", "/")
    scored: list[tuple[tuple[int, int, str], dict[str, str]]] = []
    for path_text in workspace_files:
        lower_path = path_text.lower()
        if not normalized_query:
            score = (3, len(path_text), lower_path)
        elif lower_path.startswith(normalized_query):
            score = (0, len(path_text), lower_path)
        elif f"/{normalized_query}" in lower_path:
            score = (1, len(path_text), lower_path)
        elif normalized_query in lower_path:
            score = (2, len(path_text), lower_path)
        else:
            continue
        parent = str(Path(path_text).parent).replace("\\", "/")
        description = "workspace file" if parent in {"", "."} else parent
        scored.append((score, {"path": path_text, "description": description}))
    scored.sort(key=lambda item: item[0])
    return [item for _, item in scored[:limit]]

