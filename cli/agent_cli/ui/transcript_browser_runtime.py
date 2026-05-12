from __future__ import annotations


def browser_detail_segments(raw: str) -> list[str]:
    segments: list[str] = []
    for raw_line in raw.splitlines():
        for segment in raw_line.split(" | "):
            text = segment.strip()
            if text:
                segments.append(text)
    return segments


def browser_detail_map(raw: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    segments = browser_detail_segments(raw)
    values: dict[str, list[str]] = {}
    extras: list[str] = []
    for segment in segments:
        if "=" not in segment:
            extras.append(segment)
            continue
        key, value = segment.split("=", 1)
        key_text = key.strip().lower()
        value_text = value.strip()
        if not key_text or not value_text:
            extras.append(segment)
            continue
        values.setdefault(key_text, []).append(value_text)
    return segments, values, extras


def append_browser_segments(lines: list[str], segments: list[str]) -> list[str]:
    if not segments:
        return lines
    first, *rest = segments
    lines.append(f"  └ {first}")
    lines.extend(f"    {segment}" for segment in rest)
    return lines


def take_browser_values(values: dict[str, list[str]], *keys: str) -> list[str]:
    taken: list[str] = []
    for key in keys:
        entries = values.pop(key, [])
        taken.extend(f"{key}={entry}" for entry in entries if entry)
    return taken


def format_browser_snapshot_lines(summary: str, raw: str) -> list[str]:
    lines = [summary]
    segments, values, extras = browser_detail_map(raw)
    ordered = []
    ordered.extend(take_browser_values(values, "error"))
    ordered.extend(take_browser_values(values, "ref"))
    ordered.extend(take_browser_values(values, "target"))
    ordered.extend(take_browser_values(values, "url"))
    ordered.extend(take_browser_values(values, "title"))
    ordered.extend(take_browser_values(values, "elements", "refs", "truncated", "preview", "time"))
    for key in sorted(values):
        ordered.extend(f"{key}={entry}" for entry in values[key] if entry)
    ordered.extend(extras)
    return append_browser_segments(lines, ordered or segments)


def format_browser_artifact_lines(summary: str, raw: str) -> list[str]:
    lines = [summary]
    segments, values, extras = browser_detail_map(raw)
    ordered = []
    ordered.extend(take_browser_values(values, "error"))
    ordered.extend(take_browser_values(values, "path"))
    ordered.extend(take_browser_values(values, "target", "ref"))
    ordered.extend(take_browser_values(values, "url"))
    ordered.extend(take_browser_values(values, "format", "viewport", "pages", "size", "file", "time"))
    for key in sorted(values):
        ordered.extend(f"{key}={entry}" for entry in values[key] if entry)
    ordered.extend(extras)
    return append_browser_segments(lines, ordered or segments)


def format_browser_console_lines(summary: str, raw: str) -> list[str]:
    lines = [summary]
    segments, values, extras = browser_detail_map(raw)
    ordered = []
    ordered.extend(take_browser_values(values, "error"))
    ordered.extend(take_browser_values(values, "count", "level", "msg", "levels"))
    ordered.extend(take_browser_values(values, "target", "url", "time"))
    for key in sorted(values):
        ordered.extend(f"{key}={entry}" for entry in values[key] if entry)
    ordered.extend(extras)
    return append_browser_segments(lines, ordered or segments)


def format_browser_error_lines(summary: str, raw: str) -> list[str]:
    lines = [summary]
    segments, values, extras = browser_detail_map(raw)
    ordered = []
    ordered.extend(take_browser_values(values, "error"))
    ordered.extend(take_browser_values(values, "count", "level", "msg", "levels"))
    ordered.extend(take_browser_values(values, "target", "url", "time"))
    for key in sorted(values):
        ordered.extend(f"{key}={entry}" for entry in values[key] if entry)
    ordered.extend(extras)
    return append_browser_segments(lines, ordered or segments)


def format_browser_request_lines(summary: str, raw: str) -> list[str]:
    lines = [summary]
    segments, values, extras = browser_detail_map(raw)
    ordered = []
    ordered.extend(take_browser_values(values, "error"))
    ordered.extend(take_browser_values(values, "count", "method", "status", "resource", "url", "outcome", "msg", "outcomes"))
    ordered.extend(take_browser_values(values, "target", "time"))
    for key in sorted(values):
        ordered.extend(f"{key}={entry}" for entry in values[key] if entry)
    ordered.extend(extras)
    return append_browser_segments(lines, ordered or segments)


def format_browser_activity_lines(*, summary: str, raw: str, code: str) -> list[str]:
    if code == "browser.snapshot":
        return format_browser_snapshot_lines(summary, raw)
    if code in {"browser.screenshot", "browser.pdf", "browser.download"}:
        return format_browser_artifact_lines(summary, raw)
    if code == "browser.errors":
        return format_browser_error_lines(summary, raw)
    if code == "browser.requests":
        return format_browser_request_lines(summary, raw)
    if code == "browser.console":
        return format_browser_console_lines(summary, raw)
    return append_browser_segments([summary], browser_detail_segments(raw))
