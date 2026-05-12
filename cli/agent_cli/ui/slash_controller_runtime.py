from __future__ import annotations

import re
from typing import Any, Callable


def merge_slash_matches(*match_groups: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in match_groups:
        for item in group:
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(dict(item))
    return merged


def slash_command_catalog(
    runtime: Any,
    *,
    local_slash_specs: list[dict[str, str]],
    merge_slash_matches_fn: Callable[..., list[dict[str, str]]],
) -> list[dict[str, str]]:
    runtime_catalog: list[dict[str, str]] = []
    catalog_getter = getattr(runtime, "slash_command_catalog", None)
    if callable(catalog_getter):
        try:
            runtime_catalog = [
                dict(item)
                for item in list(catalog_getter() or [])
                if isinstance(item, dict)
            ]
        except Exception:
            runtime_catalog = []
    elif callable(getattr(runtime, "slash_command_matches", None)):
        try:
            runtime_catalog = [
                dict(item)
                for item in list(runtime.slash_command_matches("") or [])
                if isinstance(item, dict)
            ]
        except Exception:
            runtime_catalog = []
    return merge_slash_matches_fn(runtime_catalog, local_slash_specs)


def slash_command_spec(command_name: str, *, slash_command_catalog_fn: Callable[[], list[dict[str, str]]]) -> dict[str, str] | None:
    normalized = str(command_name or "").strip().lower()
    if not normalized:
        return None
    for item in slash_command_catalog_fn():
        if str(item.get("name") or "").strip().lower() == normalized:
            return dict(item)
    return None


def active_nonspace_span(text: str, cursor_pos: int) -> tuple[int, int] | None:
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
    return (start, end)


def slash_completion_context(
    *,
    full_text: str,
    cursor_pos: int,
    build_context_fn: Callable[..., Any],
    active_nonspace_span_fn: Callable[[str, int], tuple[int, int] | None],
) -> Any | None:
    if not full_text.startswith("/"):
        return None
    first_line = full_text.split("\n", 1)[0]
    cursor = max(0, min(int(cursor_pos), len(first_line)))
    if cursor_pos > len(first_line):
        return None
    line_prefix = first_line[:cursor]
    if not line_prefix.startswith("/"):
        return None
    body = line_prefix[1:]
    if body.startswith(" "):
        return None
    if not body:
        replace_end = len(first_line.split(" ", 1)[0]) if first_line else 0
        return build_context_fn(
            mode="slash",
            query="",
            line_prefix=line_prefix,
            line_end=first_line,
            replace_start=0,
            replace_end=replace_end,
        )
    if " " not in body and not body.endswith(" "):
        active_span = active_nonspace_span_fn(first_line, cursor)
        if active_span is None:
            return None
        return build_context_fn(
            mode="slash",
            query=body,
            line_prefix=line_prefix,
            line_end=first_line,
            replace_start=active_span[0],
            replace_end=active_span[1],
        )
    command_name, _, rest = body.partition(" ")
    if not command_name:
        return None
    arg_text = rest
    ends_with_space = bool(line_prefix) and line_prefix[-1].isspace()
    arg_tokens = tuple(re.findall(r"\S+", arg_text))
    current_token = "" if ends_with_space else (arg_tokens[-1] if arg_tokens else "")
    if current_token:
        active_span = active_nonspace_span_fn(first_line, cursor)
        if active_span is None:
            return None
        replace_start, replace_end = active_span
    else:
        replace_start = cursor
        replace_end = cursor
    return build_context_fn(
        mode="slash_arg",
        query=current_token,
        line_prefix=line_prefix,
        line_end=first_line,
        replace_start=replace_start,
        replace_end=replace_end,
        command_name=command_name,
        arg_tokens=arg_tokens,
        current_token=current_token,
        ends_with_space=ends_with_space,
    )
