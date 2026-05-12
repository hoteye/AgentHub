from __future__ import annotations

from datetime import datetime, timezone

from shared.web_automation.types import BrowserConsoleEntry, BrowserTab

DEFAULT_CONSOLE_LIMIT = 100
MAX_CONSOLE_MESSAGES = 200


def append_console_entry(
    tab: BrowserTab,
    *,
    message_type: str,
    text: str,
    location: dict[str, int | str] | None = None,
) -> BrowserConsoleEntry:
    entry = BrowserConsoleEntry(
        type=_normalize_message_type(message_type),
        text=str(text or "").strip(),
        timestamp=_timestamp(),
        location=dict(location) if location else None,
    )
    tab.console.append(entry)
    if len(tab.console) > MAX_CONSOLE_MESSAGES:
        del tab.console[:-MAX_CONSOLE_MESSAGES]
    return entry


def read_console_entries(
    tab: BrowserTab,
    *,
    level: str | None = None,
    limit: int = DEFAULT_CONSOLE_LIMIT,
) -> list[BrowserConsoleEntry]:
    threshold = _console_priority(level) if level else None
    entries = tab.console
    if threshold is not None:
        entries = [entry for entry in entries if _console_priority(entry.type) >= threshold]
    bounded_limit = max(1, int(limit))
    return [
        BrowserConsoleEntry(
            type=entry.type,
            text=entry.text,
            timestamp=entry.timestamp,
            location=(dict(entry.location) if entry.location else None),
        )
        for entry in entries[-bounded_limit:]
    ]


def read_error_entries(
    tab: BrowserTab,
    *,
    limit: int = DEFAULT_CONSOLE_LIMIT,
) -> list[BrowserConsoleEntry]:
    bounded_limit = max(1, int(limit))
    entries = [entry for entry in tab.console if _is_error_entry(entry)]
    return [_copy_console_entry(entry) for entry in entries[-bounded_limit:]]


def read_request_entries(
    tab: BrowserTab,
    *,
    limit: int = DEFAULT_CONSOLE_LIMIT,
    outcome: str | None = None,
    method: str | None = None,
) -> list[BrowserConsoleEntry]:
    bounded_limit = max(1, int(limit))
    normalized_outcome = str(outcome or "").strip().lower()
    normalized_method = str(method or "").strip().upper()
    entries = [entry for entry in tab.console if _is_request_entry(entry)]
    if normalized_outcome:
        entries = [entry for entry in entries if _request_outcome(entry) == normalized_outcome]
    if normalized_method:
        entries = [entry for entry in entries if _request_method(entry) == normalized_method]
    return [_copy_console_entry(entry) for entry in entries[-bounded_limit:]]


def _normalize_message_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "warn":
        return "warning"
    return normalized or "info"


def _copy_console_entry(entry: BrowserConsoleEntry) -> BrowserConsoleEntry:
    return BrowserConsoleEntry(
        type=entry.type,
        text=entry.text,
        timestamp=entry.timestamp,
        location=(dict(entry.location) if entry.location else None),
    )


def _is_error_entry(entry: BrowserConsoleEntry) -> bool:
    normalized = _normalize_message_type(entry.type)
    if normalized == "error":
        return True
    location = entry.location or {}
    severity = _normalize_message_type(str(location.get("severity") or ""))
    return severity == "error"


def _is_request_entry(entry: BrowserConsoleEntry) -> bool:
    normalized = _normalize_message_type(entry.type)
    if normalized in {"request", "network", "http", "xhr", "fetch"}:
        return True
    location = entry.location or {}
    if not isinstance(location, dict):
        return False
    return any(
        str(location.get(key) or "").strip()
        for key in ("method", "status", "resource_type", "resource", "outcome", "request_id")
    )


def _request_outcome(entry: BrowserConsoleEntry) -> str:
    location = entry.location or {}
    explicit = str(location.get("outcome") or "").strip().lower()
    if explicit:
        return explicit
    status = location.get("status")
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        status_code = None
    if status_code is None:
        return ""
    return "failed" if status_code >= 400 else "ok"


def _request_method(entry: BrowserConsoleEntry) -> str:
    location = entry.location or {}
    return str(location.get("method") or "").strip().upper()


def _console_priority(level: str | None) -> int:
    normalized = _normalize_message_type(level or "")
    if normalized == "error":
        return 3
    if normalized == "warning":
        return 2
    if normalized in {"info", "log"}:
        return 1
    if normalized == "debug":
        return 0
    return 1


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
