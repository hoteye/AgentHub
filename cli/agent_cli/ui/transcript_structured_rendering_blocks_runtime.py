from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.ui.transcript_structured_access import (
    payload_code,
    payload_input,
    payload_metadata,
    payload_output,
    payload_state,
    payload_summary,
)
from cli.agent_cli.ui.transcript_structured_visual_blocks import structured_tool_block_lines


def web_search_activity_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    header: str,
    backend_header: str,
    block_lines_fn: Callable[..., list[str]] = structured_tool_block_lines,
) -> list[str]:
    return block_lines_fn(
        header,
        width=width,
        metadata=_web_search_metadata_lines(payload, backend_header=backend_header),
        details=_web_search_detail_lines(payload),
    )


def file_activity_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    header: str,
    block_lines_fn: Callable[..., list[str]] = structured_tool_block_lines,
) -> list[str]:
    return block_lines_fn(
        header,
        width=width,
        metadata=_file_activity_metadata_lines(payload),
        details=_file_activity_detail_lines(payload),
    )


def _web_search_metadata_lines(payload: dict[str, Any], *, backend_header: str) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    lines: list[str] = []
    outcome = _web_search_outcome(payload, backend_header=backend_header)
    backend = _web_search_backend(payload, backend_header=backend_header)
    count_text = _first_text(input_payload.get("count"), _detail_lookup(output_text, "count"))
    if outcome:
        lines.append(f"state: {outcome}")
    if backend:
        lines.append(f"backend: {backend}")
    if count_text:
        lines.append(f"count: {count_text}")
    return lines


def _web_search_detail_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    query_text = _first_text(
        input_payload.get("query"),
        _detail_lookup(output_text, "query"),
        _clean_summary_query(payload_summary(payload)),
    )
    details: list[str] = []
    if query_text:
        details.append(query_text)
    elif count_text := _first_text(
        input_payload.get("count"), _detail_lookup(output_text, "count")
    ):
        details.append(_count_label(count_text, singular="result", plural="results"))
    details.extend(_web_search_reason_lines(output_text))
    return details


def _web_search_outcome(payload: dict[str, Any], *, backend_header: str) -> str:
    input_payload = payload_input(payload)
    explicit = _first_text(
        input_payload.get("web_search_outcome"),
        input_payload.get("search_phase"),
        _detail_lookup(payload_output(payload), "state"),
    ).lower()
    if explicit:
        return explicit
    state = payload_state(payload)
    has_backend_or_count = bool(
        _web_search_backend(payload, backend_header=backend_header)
        or _first_text(input_payload.get("count"), _detail_lookup(payload_output(payload), "count"))
    )
    if state == "running" and has_backend_or_count:
        return "search_dispatched"
    if state == "completed" and has_backend_or_count:
        return "search_results_received"
    if state == "error" and has_backend_or_count:
        return "search_failed"
    return ""


def _web_search_backend(payload: dict[str, Any], *, backend_header: str) -> str:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    backend = _first_text(input_payload.get("backend"), metadata.get("backend")).lower()
    if backend in {"native", "local"}:
        return backend
    if bool(input_payload.get("provider_native")):
        return "native"
    title = str(backend_header or "").lower()
    if title.startswith("native web search"):
        return "native"
    if title.startswith("local web search"):
        return "local"
    return ""


def _web_search_reason_lines(output_text: str) -> list[str]:
    reasons: list[str] = []
    for line in _detail_lines(output_text):
        lowered = line.lower()
        if lowered.startswith(("query=", "count=", "state=", "backend=")):
            continue
        if _looks_like_ranked_web_result(line):
            continue
        if line.startswith("reason="):
            reasons.append(f"reason: {line.partition('=')[2].strip()}")
        elif "=" in line:
            reasons.append(line.replace("=", ": ", 1))
        else:
            reasons.append(f"reason: {line}")
    return reasons


def _file_activity_metadata_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    lines: list[str] = []
    count_text = _first_text(input_payload.get("count"), _detail_lookup(output_text, "count"))
    if count_text:
        lines.append(f"count: {count_text}")
    if truncated := _first_text(
        input_payload.get("truncated"), _detail_lookup(output_text, "truncated")
    ):
        lines.append(f"truncated: {truncated}")
    return lines


def _file_activity_detail_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    code = payload_code(payload)
    if code in {"dir.search", "file.search"}:
        subject = _search_subject(
            _first_text(
                input_payload.get("query"),
                input_payload.get("pattern"),
                _detail_lookup(output_text, "query"),
                _detail_lookup(output_text, "pattern"),
            ),
            _first_text(
                input_payload.get("path"),
                input_payload.get("dir_path"),
                _detail_lookup(output_text, "path"),
                _detail_lookup(output_text, "dir_path"),
            ),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    if code in {"dir.list", "file.list"}:
        subject = _first_text(
            input_payload.get("path"),
            input_payload.get("dir_path"),
            _detail_lookup(output_text, "path"),
            _detail_lookup(output_text, "dir_path"),
            payload_summary(payload),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    if code == "file.read":
        subject = _first_text(
            input_payload.get("file_path"),
            input_payload.get("path"),
            _detail_lookup(output_text, "file_path"),
            _detail_lookup(output_text, "path"),
            _first_detail_segment(output_text),
            payload_summary(payload),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    return _non_metadata_detail_lines(output_text)


def _detail_lookup(output_text: str, *keys: str) -> str:
    key_set = {str(key).strip().lower() for key in keys if str(key).strip()}
    for line in _detail_lines(output_text):
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() in key_set and value.strip():
            return value.strip()
    return ""


def _detail_lines(output_text: str) -> list[str]:
    return [line.strip() for line in str(output_text or "").splitlines() if line.strip()]


def _non_metadata_detail_lines(output_text: str) -> list[str]:
    lines: list[str] = []
    for line in _detail_lines(output_text):
        key = line.partition("=")[0].strip().lower()
        if key in {"count", "query", "pattern", "path", "dir_path", "file_path", "truncated"}:
            continue
        lines.append(line)
    return lines


def _first_detail_segment(output_text: str) -> str:
    for line in _detail_lines(output_text):
        first_segment = line.split(" | ", maxsplit=1)[0].strip()
        if first_segment and "=" not in first_segment:
            return first_segment
    return ""


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_summary_query(summary: str) -> str:
    text = str(summary or "").strip()
    if text.lower().startswith(("query=", "pattern=")):
        return text.partition("=")[2].strip()
    return text


def _search_subject(query: str, path: str) -> str:
    if query and path:
        return f"{query} in {path}"
    return query or path


def _count_label(count_text: str, *, singular: str, plural: str) -> str:
    label = singular if str(count_text).strip() == "1" else plural
    return f"{count_text} {label}"


def _looks_like_ranked_web_result(line: str) -> bool:
    stripped = str(line or "").strip()
    index, separator, _rest = stripped.partition(". ")
    return bool(separator and index.isdigit())
