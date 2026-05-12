from __future__ import annotations

import statistics
from typing import Any

from cli.scripts.probe_native_web_search_backend_probes import _response_text_preview

PROBE_CACHE_SCHEMA_VERSION = "web_search_probe_cache/v1"
PROBE_TOOL_KEY = "web_search"


def _summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        grouped.setdefault(str(item.get("status") or "unknown"), []).append(item)
    rows: list[dict[str, Any]] = []
    for status, items in sorted(grouped.items()):
        latencies = [int(item.get("elapsed_ms") or 0) for item in items if int(item.get("elapsed_ms") or 0) > 0]
        rows.append(
            {
                "status": status,
                "count": len(items),
                "avg_elapsed_ms": round(statistics.mean(latencies), 1) if latencies else None,
            }
        )
    return rows


def _cache_availability_for_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"supported", "unsupported", "error"}:
        return normalized
    return "unknown"


def _cache_confidence_for_result(item: dict[str, Any]) -> str:
    normalized = str(item.get("confidence") or "").strip().lower()
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "low"


def _cache_ttl_for_status(status: str, *, default_ttl_seconds: int) -> int:
    normalized = str(status or "").strip().lower()
    base = max(0, int(default_ttl_seconds))
    if normalized in {"error", "no_probe_adapter"}:
        return min(base, 600)
    return base


def _selected_backend_for_probe_result(item: dict[str, Any]) -> str:
    from cli.agent_cli.tools_core.tool_backend_registry import (
        BACKEND_LOCAL_WEB_SEARCH,
        BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
        BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
        BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
    )

    status = str(item.get("status") or "").strip().lower()
    if status != "supported":
        return BACKEND_LOCAL_WEB_SEARCH
    transport_family = str(item.get("transport_family") or "").strip().lower()
    provider_name = str(item.get("provider_name") or item.get("provider") or "").strip().lower()
    if transport_family == "openai_responses":
        return BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    if transport_family == "anthropic_messages":
        return BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
    if provider_name in {"glm", "zhipu"}:
        return BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH
    return BACKEND_LOCAL_WEB_SEARCH


def _probe_cache_record(item: dict[str, Any], *, default_ttl_seconds: int) -> tuple[str, dict[str, Any]]:
    from cli.agent_cli.tools_core.tool_capabilities import (
        utc_now_iso,
        web_search_probe_cache_key,
        web_search_probe_cache_value,
    )

    provider_name = str(item.get("provider_name") or item.get("provider") or "").strip().lower()
    model = str(item.get("model") or "").strip().lower()
    wire_api = str(item.get("wire_api") or "").strip().lower()
    planner_kind = str(item.get("planner_kind") or "").strip().lower()
    status = str(item.get("status") or "").strip().lower()
    issue = str(item.get("issue") or "").strip()
    cache_key = web_search_probe_cache_key(
        provider_name=provider_name,
        model=model,
        wire_api=wire_api,
        planner_kind=planner_kind,
    )
    if status == "supported":
        reason = "probe_report_native_supported"
    elif status == "unsupported":
        reason = "probe_report_native_unsupported"
    else:
        reason = "probe_report_uncertain"
    if issue:
        reason = f"{reason}: {issue[:120]}"
    cache_value = web_search_probe_cache_value(
        selected_backend=_selected_backend_for_probe_result(item),
        availability=_cache_availability_for_status(status),
        confidence=_cache_confidence_for_result(item),
        checked_at=str(item.get("checked_at") or "").strip() or utc_now_iso(),
        ttl_seconds=_cache_ttl_for_status(status, default_ttl_seconds=default_ttl_seconds),
        reason=reason,
        probe_status=status if status else "unknown",
        source="probe_script",
    )
    return (
        cache_key.as_lookup_key(),
        {
            "tool": PROBE_TOOL_KEY,
            "capability_key": PROBE_TOOL_KEY,
            "selected_backend": cache_value.selected_backend,
            "availability": cache_value.availability,
            "confidence": cache_value.confidence,
            "checked_at": cache_value.checked_at,
            "ttl_seconds": int(cache_value.ttl_seconds),
            "expires_at": cache_value.expires_at(),
            "reason": cache_value.reason,
            "probe_status": cache_value.probe_status,
            "source": cache_value.source,
        },
    )


def _probe_cache_payload(results: list[dict[str, Any]], *, default_ttl_seconds: int) -> dict[str, Any]:
    from cli.agent_cli.tools_core.tool_capabilities import utc_now_iso

    entries: dict[str, dict[str, Any]] = {}
    for item in results:
        cache_key, cache_record = _probe_cache_record(item, default_ttl_seconds=default_ttl_seconds)
        entries[cache_key] = cache_record
    return {
        "version": PROBE_CACHE_SCHEMA_VERSION,
        "tool": PROBE_TOOL_KEY,
        "capability_key": PROBE_TOOL_KEY,
        "generated_at": utc_now_iso(),
        "default_ttl_seconds": max(0, int(default_ttl_seconds)),
        "entry_count": len(entries),
        "entries": entries,
    }


def _mode_cell(item: dict[str, Any]) -> str:
    requested = str(item.get("requested_mode") or "").strip()
    effective = str(item.get("effective_mode") or "").strip()
    if requested and effective and requested != effective:
        return f"{requested}->{effective}"
    return effective or requested


def _print_table(results: list[dict[str, Any]]) -> None:
    headers = ("CASE", "STATUS", "CONF", "MODE", "SUPPORT", "FAMILY", "MS", "MARKERS", "ISSUE")
    rows = [headers]
    for item in results:
        rows.append(
            (
                str(item.get("case") or ""),
                str(item.get("status") or ""),
                str(item.get("confidence") or ""),
                _mode_cell(item),
                str(item.get("mode_support_level") or ""),
                str(item.get("transport_family") or item.get("wire_api") or ""),
                str(item.get("elapsed_ms") or ""),
                ",".join(str(marker) for marker in list(item.get("native_markers") or [])[:3]),
                _response_text_preview(item.get("issue"), max_chars=90),
            )
        )
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(headers))]
    for row_index, row in enumerate(rows):
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            print("  ".join("-" * width for width in widths))
