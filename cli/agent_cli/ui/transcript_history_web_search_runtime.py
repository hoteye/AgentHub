from __future__ import annotations

import re
from typing import Any

from cli.agent_cli.models import ActivityEvent


def _activity_params(event: ActivityEvent) -> dict[str, Any]:
    return dict(getattr(event, "params", None) or {})


def web_search_detail_lines(detail_text: str) -> list[str]:
    return [line.strip() for line in str(detail_text or "").splitlines() if line.strip()]


def web_search_backend(event: ActivityEvent) -> str:
    params = _activity_params(event)
    backend = str(params.get("backend") or "").strip().lower()
    if backend in {"native", "local"}:
        return backend
    if bool(params.get("provider_native")):
        return "native"
    title = str(event.title or "").strip().lower()
    if title.startswith("native web search"):
        return "native"
    if title.startswith("local web search"):
        return "local"
    return ""


def web_search_query(event: ActivityEvent, detail_lines: list[str]) -> str:
    params = _activity_params(event)
    query_text = str(params.get("query") or "").strip()
    if query_text:
        return query_text
    for line in detail_lines:
        if line.startswith("query="):
            return line.partition("=")[2].strip()
    return ""


def web_search_count(event: ActivityEvent, detail_lines: list[str]) -> str:
    params = _activity_params(event)
    count_text = str(params.get("count") or "").strip()
    if count_text:
        return count_text
    for line in detail_lines:
        if line.startswith("count="):
            return line.partition("=")[2].strip()
    return ""


def _explicit_web_search_outcome(event: ActivityEvent) -> str:
    params = _activity_params(event)
    outcome = str(params.get("web_search_outcome") or params.get("search_phase") or "").strip().lower()
    if outcome in {
        "search_dispatched",
        "search_results_received",
        "provider_error_without_search",
        "native_interrupted",
        "fallback_after_native_failure",
        "search_failed",
    }:
        return outcome
    search_results_received = params.get("search_results_received")
    if search_results_received is True:
        return "search_results_received"
    if search_results_received is False and params.get("search_dispatched") is True:
        backend = web_search_backend(event)
        return "native_interrupted" if backend == "native" else "fallback_after_native_failure"
    if params.get("search_dispatched") is True:
        return "search_dispatched"
    return ""


def web_search_outcome(event: ActivityEvent, detail_lines: list[str], *, backend: str) -> str:
    explicit = _explicit_web_search_outcome(event)
    if explicit:
        return explicit
    if event.status == "running":
        return "search_dispatched"
    if event.status == "success":
        return "search_results_received"
    detail_text = "\n".join(detail_lines).lower()
    if "fallback_after_native_failure" in detail_text:
        return "fallback_after_native_failure"
    if any(
        marker in detail_text
        for marker in {
            "before web_search_call dispatch",
            "marker was absent",
            "accepted without server_tool_use dispatch",
            "server_tool_use_missing",
        }
    ):
        return "provider_error_without_search"
    if any(
        marker in detail_text
        for marker in {
            "native_interrupted",
            "server_tool_result_missing",
            "web_search_tool_result_empty",
            "without matching web_search_tool_result",
            "without usable structured results",
            "before usable results were received",
            "provider-side error without usable results",
            "fallback_reason=",
            "native_request_error",
        }
    ):
        return "native_interrupted" if backend == "native" else "fallback_after_native_failure"
    return "search_failed"


def _web_search_reason_line(detail_lines: list[str]) -> str:
    for line in detail_lines:
        if line.startswith("query=") or line.startswith("count="):
            continue
        if re.match(r"^\d+\.\s+", line):
            continue
        text = str(line).strip()
        if not text or text == "web_search failed":
            continue
        if "=" in text:
            return text
        return f"reason={text}"
    return ""


def web_search_activity_lines(event: ActivityEvent) -> list[str]:
    summary = str(event.title or "").strip()
    if not summary:
        return []
    detail_lines = web_search_detail_lines(str(event.detail or ""))
    query_text = web_search_query(event, detail_lines)
    backend = web_search_backend(event)
    outcome = web_search_outcome(event, detail_lines, backend=backend)
    count_text = web_search_count(event, detail_lines)
    metadata_parts = [f"state={outcome}"]
    if backend:
        metadata_parts.append(f"backend={backend}")
    if outcome == "search_results_received" and count_text:
        metadata_parts.append(f"count={count_text}")
    lines = [summary]
    if query_text:
        lines.append(f"  └ {query_text}")
        if metadata_parts:
            lines.append(f"    {' | '.join(metadata_parts)}")
    elif metadata_parts:
        lines.append(f"  └ {' | '.join(metadata_parts)}")
    reason_line = _web_search_reason_line(detail_lines)
    if reason_line:
        lines.append(f"    {reason_line}")
    return lines


def uses_compact_web_search_cell(event: ActivityEvent) -> bool:
    title = str(event.title or "").strip().lower()
    if event.status == "running":
        return True
    return title.startswith("native web search") or title.startswith("local web search")
