from __future__ import annotations

from collections.abc import Iterable

from cli.agent_cli.ui.transcript_visual_rendering_helpers import wrap_prefixed_text


def structured_tool_block_lines(
    header: str,
    *,
    width: int,
    metadata: Iterable[str] = (),
    details: Iterable[str] = (),
    empty_detail: str = "",
) -> list[str]:
    lines = wrap_prefixed_text(
        str(header or "Tool").strip() or "Tool",
        first_prefix="• ",
        continuation_prefix="  ",
        width=width,
    )
    for metadata_line in _nonempty_lines(metadata):
        lines.extend(
            wrap_prefixed_text(
                metadata_line,
                first_prefix="  │ ",
                continuation_prefix="  │ ",
                width=width,
            )
        )
    detail_lines = _nonempty_lines(details)
    if not detail_lines and empty_detail:
        detail_lines = [str(empty_detail).strip()]
    for index, detail_line in enumerate(detail_lines):
        lines.extend(
            wrap_prefixed_text(
                detail_line,
                first_prefix="  └ " if index == 0 else "    ",
                continuation_prefix="    ",
                width=width,
            )
        )
    return lines


def _nonempty_lines(values: Iterable[str]) -> list[str]:
    lines: list[str] = []
    for value in values:
        for line in str(value or "").splitlines():
            text = line.rstrip()
            if text.strip():
                lines.append(text)
    return lines
