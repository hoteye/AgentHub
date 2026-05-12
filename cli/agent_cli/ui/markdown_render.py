from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from markdown_it import MarkdownIt
from cli.agent_cli.ui import markdown_render_runtime

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    from pygments.token import Comment, Keyword, Name, Number, Operator, String as PygmentsString
except Exception:  # pragma: no cover - optional dependency fallback
    lex = None
    get_lexer_by_name = None
    ClassNotFound = Exception
    Comment = Keyword = Name = Number = Operator = PygmentsString = None


_INLINE_MARKDOWN = MarkdownIt("commonmark")
_FENCE_RE = re.compile(r"^(?P<indent>\s*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-+*]|\d+[.)])\s+(?P<body>.*)$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_LEXER_ALIASES = {
    "jsonc": "json",
    "shell": "bash",
    "shellscript": "bash",
}


@dataclass(slots=True)
class MarkdownSpan:
    start: int
    end: int
    kind: str


@dataclass(slots=True)
class RenderedMarkdownLine:
    text: str
    spans: list[MarkdownSpan]


@dataclass(slots=True)
class _FenceState:
    fence_char: str
    fence_len: int
    language: str | None
    lines: list[str]


def render_markdown_lines(content: str) -> list[str]:
    return [line.text for line in render_markdown_visual_lines(content)]


def render_markdown_visual_lines(content: str) -> list[RenderedMarkdownLine]:
    source_lines = str(content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rendered: list[RenderedMarkdownLine] = []
    fence: _FenceState | None = None

    for raw_line in source_lines:
        if fence is not None:
            stripped = raw_line.lstrip()
            if stripped.startswith(fence.fence_char * fence.fence_len):
                rendered.extend(_render_fenced_code_lines(fence.lines, fence.language))
                fence = None
                continue
            fence.lines.append(raw_line)
            continue

        line = raw_line.rstrip()
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            fence_token = fence_match.group("fence")
            fence = _FenceState(
                fence_char=fence_token[0],
                fence_len=len(fence_token),
                language=_parse_fence_language(fence_match.group("info") or ""),
                lines=[],
            )
            continue

        if not line.strip():
            rendered.append(RenderedMarkdownLine("", []))
            continue

        if _is_indented_code_block(line):
            rendered.append(RenderedMarkdownLine(raw_line, []))
            continue

        rendered.append(_render_markdown_source_line(line))

    if fence is not None:
        rendered.extend(_render_fenced_code_lines(fence.lines, fence.language))

    return _trim_blank_lines(rendered)


def _render_fenced_code_lines(lines: list[str], language: str | None) -> list[RenderedMarkdownLine]:
    if not lines:
        return []
    if not language:
        return [RenderedMarkdownLine(line, []) for line in lines]
    highlighted = _highlight_code_lines("\n".join(lines), language)
    if highlighted is None:
        return [RenderedMarkdownLine(line, []) for line in lines]
    return highlighted


def _parse_fence_language(info: str) -> str | None:
    first = str(info or "").strip().split(maxsplit=1)[0] if str(info or "").strip() else ""
    if not first:
        return None
    language = first.split(",", 1)[0].strip().lower()
    return language or None


@lru_cache(maxsize=64)
def _lexer_for_language(language: str):
    if get_lexer_by_name is None:
        return None
    language = _LEXER_ALIASES.get(language.lower(), language.lower())
    try:
        return get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def _highlight_code_lines(code: str, language: str) -> list[RenderedMarkdownLine] | None:
    lexer = _lexer_for_language(language)
    if lexer is None or lex is None:
        return None
    texts = [""]
    spans: list[list[MarkdownSpan]] = [[]]
    for token_type, value in lex(code, lexer):
        kind = _syntax_kind_for_token(token_type)
        parts = str(value or "").split("\n")
        for index, part in enumerate(parts):
            line_index = len(texts) - 1
            if part:
                start = len(texts[line_index])
                texts[line_index] += part
                end = len(texts[line_index])
                if kind is not None:
                    spans[line_index].append(MarkdownSpan(start, end, kind))
            if index < len(parts) - 1:
                texts.append("")
                spans.append([])
    while len(texts) > 1 and texts[-1] == "" and spans[-1] == []:
        texts.pop()
        spans.pop()
    return [
        RenderedMarkdownLine(text, _merge_adjacent_spans(line_spans))
        for text, line_spans in zip(texts, spans)
    ]


def _syntax_kind_for_token(token_type) -> str | None:
    if Comment is None:
        return None
    if token_type in Comment:
        return "syntax_comment"
    if token_type in Keyword:
        return "syntax_keyword"
    if token_type in PygmentsString:
        return "syntax_string"
    if token_type in Number:
        return "syntax_number"
    if token_type in Operator:
        return "syntax_operator"
    if token_type in Name.Function or token_type in Name.Class or token_type in Name.Namespace:
        return "syntax_name"
    if token_type in Name.Builtin or token_type in Name.Decorator or token_type in Name.Exception:
        return "syntax_builtin"
    return None


def _merge_adjacent_spans(spans: list[MarkdownSpan]) -> list[MarkdownSpan]:
    return markdown_render_runtime.merge_adjacent_spans(
        spans,
        span_factory=lambda start, end, kind: MarkdownSpan(start, end, kind),
    )


def _render_markdown_source_line(line: str) -> RenderedMarkdownLine:
    return markdown_render_runtime.render_markdown_source_line(
        line,
        hr_match=bool(_HR_RE.match(line)),
        split_blockquote_prefix_fn=_split_blockquote_prefix,
        render_non_quote_line_fn=_render_non_quote_line,
        add_span_fn=_add_span,
        prefixed_rendered_line_fn=_prefixed_rendered_line,
        styled_line_fn=lambda text, kind: _styled_line(text, kind=kind),
        line_factory=lambda text, spans: RenderedMarkdownLine(text, spans),
    )


def _render_non_quote_line(line: str) -> RenderedMarkdownLine:
    return markdown_render_runtime.render_non_quote_line(
        line,
        heading_match=_HEADING_RE.match(line),
        list_match=_LIST_RE.match(line),
        render_inline_text_fn=_render_inline_text,
        prefixed_rendered_line_fn=_prefixed_rendered_line,
        rstrip_rendered_line_fn=_rstrip_rendered_line,
        add_span_fn=_add_span,
        normalize_list_marker_fn=_normalize_list_marker,
    )


def _split_blockquote_prefix(line: str) -> tuple[str, str]:
    return markdown_render_runtime.split_blockquote_prefix(line)


def _normalize_list_marker(marker: str) -> str:
    return markdown_render_runtime.normalize_list_marker(marker)


def _render_inline_text(text: str) -> RenderedMarkdownLine:
    inline_tokens = _INLINE_MARKDOWN.parseInline(text)
    children = []
    for token in inline_tokens:
        if token.type == "inline":
            children.extend(token.children or [])
        else:
            children.append(token)
    if not children:
        return RenderedMarkdownLine(text, [])
    return _flatten_inline_tokens(children)


def _flatten_inline_tokens(tokens: list) -> RenderedMarkdownLine:
    return markdown_render_runtime.flatten_inline_tokens(
        tokens,
        line_factory=lambda text, spans: RenderedMarkdownLine(text, spans),
        span_factory=lambda start, end, kind: MarkdownSpan(start, end, kind),
    )


def _trim_blank_lines(lines: list[RenderedMarkdownLine]) -> list[RenderedMarkdownLine]:
    return markdown_render_runtime.trim_blank_lines(
        lines,
        empty_line_factory=lambda: RenderedMarkdownLine("", []),
    )


def _is_indented_code_block(line: str) -> bool:
    return line.startswith("    ") or line.startswith("\t")


def _styled_line(text: str, *, kind: str) -> RenderedMarkdownLine:
    spans = [MarkdownSpan(0, len(text), kind)] if text else []
    return RenderedMarkdownLine(text, spans)


def _add_span(line: RenderedMarkdownLine, start: int, end: int, kind: str) -> RenderedMarkdownLine:
    bounded_start = max(0, min(start, len(line.text)))
    bounded_end = max(0, min(end, len(line.text)))
    if bounded_end <= bounded_start:
        return line
    return RenderedMarkdownLine(line.text, [*line.spans, MarkdownSpan(bounded_start, bounded_end, kind)])


def _prefixed_rendered_line(line: RenderedMarkdownLine, prefix: str) -> RenderedMarkdownLine:
    if not prefix:
        return line
    shift = len(prefix)
    return RenderedMarkdownLine(
        f"{prefix}{line.text}",
        [MarkdownSpan(span.start + shift, span.end + shift, span.kind) for span in line.spans],
    )


def _rstrip_rendered_line(line: RenderedMarkdownLine) -> RenderedMarkdownLine:
    trimmed = line.text.rstrip()
    if len(trimmed) == len(line.text):
        return line
    kept = len(trimmed)
    spans: list[MarkdownSpan] = []
    for span in line.spans:
        start = min(span.start, kept)
        end = min(span.end, kept)
        if end > start:
            spans.append(MarkdownSpan(start, end, span.kind))
    return RenderedMarkdownLine(trimmed, spans)
