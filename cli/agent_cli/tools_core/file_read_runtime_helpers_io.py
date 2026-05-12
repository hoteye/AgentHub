from __future__ import annotations

from collections import deque
from typing import Any, Callable, List


def indentation_mode_records_impl(
    records: List[Any],
    *,
    offset: int,
    limit: int,
    indentation: dict[str, Any] | None,
    file_tool_error_cls: type[Exception],
    effective_indents_fn: Callable[[List[Any]], List[int]],
    trim_empty_line_records_fn: Callable[[deque[Any]], None],
    tab_width: int,
) -> List[Any]:
    if offset <= 0:
        raise file_tool_error_cls("offset must be a 1-indexed line number")
    if limit <= 0:
        raise file_tool_error_cls("limit must be greater than zero")
    if not records:
        raise file_tool_error_cls("anchor_line exceeds file length")

    options = dict(indentation or {})
    anchor_line = int(options.get("anchor_line") or offset)
    if anchor_line <= 0:
        raise file_tool_error_cls("anchor_line must be a 1-indexed line number")
    if anchor_line > len(records):
        raise file_tool_error_cls("anchor_line exceeds file length")

    max_levels = int(options.get("max_levels") or 0)
    include_siblings = bool(options.get("include_siblings", False))
    include_header = bool(options.get("include_header", True))
    max_lines = options.get("max_lines")
    guard_limit = int(max_lines or limit)
    if guard_limit <= 0:
        raise file_tool_error_cls("max_lines must be greater than zero")

    effective = effective_indents_fn(records)
    anchor_index = anchor_line - 1
    anchor_indent = effective[anchor_index]
    min_indent = 0 if max_levels == 0 else max(0, anchor_indent - (max_levels * tab_width))
    final_limit = min(limit, guard_limit, len(records))

    if final_limit == 1:
        return [records[anchor_index]]

    out: deque[Any] = deque([records[anchor_index]])
    i = anchor_index - 1
    j = anchor_index + 1
    i_min_indent_hits = 0
    j_min_indent_hits = 0

    while len(out) < final_limit:
        progressed = 0

        if i >= 0:
            if effective[i] >= min_indent:
                record = records[i]
                out.appendleft(record)
                progressed += 1
                i -= 1

                if effective[i + 1] == min_indent and not include_siblings:
                    allow_header_comment = include_header and record.is_comment()
                    can_take_line = allow_header_comment or i_min_indent_hits == 0
                    if can_take_line:
                        i_min_indent_hits += 1
                    else:
                        out.popleft()
                        progressed -= 1
                        i = -1
                if len(out) >= final_limit:
                    break
            else:
                i = -1

        if j < len(records):
            if effective[j] >= min_indent:
                record = records[j]
                out.append(record)
                progressed += 1
                j += 1

                if effective[j - 1] == min_indent and not include_siblings:
                    if j_min_indent_hits > 0:
                        out.pop()
                        progressed -= 1
                        j = len(records)
                    j_min_indent_hits += 1
            else:
                j = len(records)

        if progressed == 0:
            break

    trim_empty_line_records_fn(out)
    return list(out)
