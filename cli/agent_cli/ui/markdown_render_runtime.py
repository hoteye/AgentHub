from __future__ import annotations

from typing import Any, Callable


def merge_adjacent_spans(spans: list[Any], *, span_factory: Callable[[int, int, str], Any]) -> list[Any]:
    if not spans:
        return []
    merged: list[Any] = [spans[0]]
    for span in spans[1:]:
        previous = merged[-1]
        if previous.kind == span.kind and previous.end == span.start:
            merged[-1] = span_factory(previous.start, span.end, span.kind)
            continue
        merged.append(span)
    return merged


def split_blockquote_prefix(line: str) -> tuple[str, str]:
    remaining = line
    depth = 0
    while True:
        stripped = remaining.lstrip()
        if not stripped.startswith(">"):
            break
        depth += 1
        stripped = stripped[1:]
        if stripped.startswith(" "):
            stripped = stripped[1:]
        remaining = stripped
    if depth == 0:
        return "", line
    return ("> " * depth), remaining


def normalize_list_marker(marker: str) -> str:
    if marker and marker[0].isdigit():
        return f"{marker[:-1]}."
    return "-"


def flatten_inline_tokens(
    tokens: list[Any],
    *,
    line_factory: Callable[[str, list[Any]], Any],
    span_factory: Callable[[int, int, str], Any],
) -> Any:
    parts: list[str] = []
    spans: list[Any] = []
    link_stack: list[tuple[str, int]] = []
    emphasis_stack: list[int] = []
    strong_stack: list[int] = []
    current_length = 0

    def append_text(value: str, *, kind: str | None = None) -> None:
        nonlocal current_length
        if not value:
            return
        start = current_length
        parts.append(value)
        current_length += len(value)
        if kind is not None:
            spans.append(span_factory(start, current_length, kind))

    for token in tokens:
        token_type = str(token.type or "")
        if token_type in {"text", "code_inline", "html_inline", "html_block"}:
            append_text(token.content or "", kind="code" if token_type == "code_inline" else None)
            continue
        if token_type == "image":
            append_text(token.content or token.attrGet("alt") or "")
            continue
        if token_type == "softbreak":
            append_text(" ")
            continue
        if token_type == "hardbreak":
            parts.append("")
            continue
        if token_type == "em_open":
            emphasis_stack.append(current_length)
            continue
        if token_type == "em_close":
            if emphasis_stack:
                start = emphasis_stack.pop()
                if current_length > start:
                    spans.append(span_factory(start, current_length, "emphasis"))
            continue
        if token_type == "strong_open":
            strong_stack.append(current_length)
            continue
        if token_type == "strong_close":
            if strong_stack:
                start = strong_stack.pop()
                if current_length > start:
                    spans.append(span_factory(start, current_length, "strong"))
            continue
        if token_type == "link_open":
            link_stack.append((token.attrGet("href") or "", current_length))
            continue
        if token_type == "link_close":
            if not link_stack:
                continue
            href, _start = link_stack.pop()
            if href:
                append_text(" (")
                append_text(href, kind="link")
                append_text(")")
            continue
        if token.content:
            append_text(token.content)

    spans.sort(key=lambda span: (span.start, span.end, span.kind))
    return line_factory("".join(parts), spans)


def trim_blank_lines(lines: list[Any], *, empty_line_factory: Callable[[], Any]) -> list[Any]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].text.strip():
        start += 1
    while end > start and not lines[end - 1].text.strip():
        end -= 1
    trimmed = lines[start:end]
    return trimmed or [empty_line_factory()]


def render_non_quote_line(
    line: str,
    *,
    heading_match: Any,
    list_match: Any,
    render_inline_text_fn: Callable[[str], Any],
    prefixed_rendered_line_fn: Callable[[Any, str], Any],
    rstrip_rendered_line_fn: Callable[[Any], Any],
    add_span_fn: Callable[[Any, int, int, str], Any],
    normalize_list_marker_fn: Callable[[str], str],
) -> Any:
    if heading_match:
        rendered = rstrip_rendered_line_fn(
            prefixed_rendered_line_fn(render_inline_text_fn(heading_match.group(2)), f"{heading_match.group(1)} ")
        )
        return add_span_fn(rendered, 0, len(rendered.text), f"heading{len(heading_match.group(1))}")

    if list_match:
        indent = list_match.group("indent")
        raw_marker = list_match.group("marker")
        marker = normalize_list_marker_fn(raw_marker)
        body = render_inline_text_fn(list_match.group("body"))
        rendered = rstrip_rendered_line_fn(prefixed_rendered_line_fn(body, f"{indent}{marker} "))
        if raw_marker and raw_marker[0].isdigit():
            return add_span_fn(rendered, 0, len(f"{indent}{marker} "), "ordered_list_marker")
        return rendered

    return rstrip_rendered_line_fn(render_inline_text_fn(line))


def render_markdown_source_line(
    line: str,
    *,
    hr_match: bool,
    split_blockquote_prefix_fn: Callable[[str], tuple[str, str]],
    render_non_quote_line_fn: Callable[[str], Any],
    add_span_fn: Callable[[Any, int, int, str], Any],
    prefixed_rendered_line_fn: Callable[[Any, str], Any],
    styled_line_fn: Callable[[str, str], Any],
    line_factory: Callable[[str, list[Any]], Any],
) -> Any:
    if hr_match:
        return line_factory("———", [])

    quote_prefix, remainder = split_blockquote_prefix_fn(line)
    if quote_prefix:
        body = render_non_quote_line_fn(remainder)
        if body.text:
            return add_span_fn(
                prefixed_rendered_line_fn(body, quote_prefix),
                0,
                len(f"{quote_prefix}{body.text}"),
                "blockquote",
            )
        return styled_line_fn(quote_prefix, "blockquote")

    return render_non_quote_line_fn(line)
