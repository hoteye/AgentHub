from __future__ import annotations

from pathlib import Path
from typing import Any


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _boolish(value: Any) -> bool | None:
    text = _normalized_text(value).lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return None


def _short_path(value: str) -> str:
    text = _normalized_text(value)
    if not text:
        return ""
    try:
        path = Path(text)
        return path.name or text
    except Exception:
        return text


def _cwd_segment(value: Any) -> str:
    text = _normalized_text(value)
    if not text or text == "-":
        return ""
    home = str(Path.home())
    if home and (text == home or text.startswith(f"{home}/")):
        return "~" + text[len(home) :]
    return text


def _provider_segments(data: dict[str, Any], *, cwd: Any = None) -> list[str]:
    provider_ready = _boolish(data.get("provider_ready"))
    segments: list[str] = []
    if provider_ready is not False:
        provider_name = _normalized_text(data.get("provider_name"))
        provider_model = _normalized_text(data.get("provider_model"))
        provider_reasoning_effort = _normalized_text(data.get("provider_reasoning_effort"))

        if provider_name and provider_name not in {"-", "fallback"}:
            segments.append(provider_name)
        if provider_model and provider_model != "-":
            segments.append(provider_model)
        if provider_reasoning_effort and provider_reasoning_effort != "-":
            segments.append(provider_reasoning_effort)
    cwd_text = _cwd_segment(cwd if cwd is not None else data.get("cwd"))
    if cwd_text:
        segments.append(cwd_text)
    return segments


def summary_segments(*, status_data: dict[str, Any], cwd: str | None = None) -> list[str]:
    data = dict(status_data or {})
    segments: list[str] = []

    provider_ready = _boolish(data.get("provider_ready"))
    provider_model = _normalized_text(data.get("provider_model"))
    if provider_ready is not False and provider_model and provider_model != "-":
        segments.append(provider_model)
    else:
        provider_name = _normalized_text(data.get("provider_name"))
        if provider_ready is not False and provider_name and provider_name not in {"-", "fallback"}:
            segments.append(provider_name)

    thread_name = _normalized_text(data.get("thread_name"))
    if thread_name and thread_name != "-":
        segments.append(thread_name)

    workspace = _short_path(cwd or data.get("cwd"))
    if workspace and workspace != "-":
        segments.append(workspace)

    thread_id = _normalized_text(data.get("thread_id"))
    if thread_id and thread_id != "-" and not thread_name:
        segments.append(thread_id[:12])

    return [segment for segment in segments if segment]


def build_provider_summary_text(
    *,
    status_data: dict[str, Any],
    cwd: str | None = None,
    separator: str = " · ",
) -> str:
    return separator.join(_provider_segments(dict(status_data or {}), cwd=cwd))


def build_status_summary_text(
    *,
    status_data: dict[str, Any],
    cwd: str | None = None,
    separator: str = " · ",
) -> str:
    return separator.join(summary_segments(status_data=status_data, cwd=cwd))
