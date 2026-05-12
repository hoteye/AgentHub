from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Any, Dict, Iterable, List, Mapping

EVENT_SCHEMA_VERSION = "v1"

# Additive taxonomy for memory governance/audit instrumentation.
MEMORY_AUDIT_EVENT_TAXONOMY = {
    "memory_upserted",
    "memory_archived",
    "memory_deleted",
    "memory_hit",
    "memory_recall_evaluated",
    "memory_recall_blocked",
    "memory_save_candidate_generated",
    "memory_save_accepted",
    "memory_save_rejected",
    "memory_save_blocked",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(item) for item in values)
    rank = max(1, ceil((percentile / 100.0) * len(ordered)))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def normalize_event_type(event_type: Any, *, fallback: str = "memory_recall_evaluated") -> str:
    value = str(event_type or "").strip()
    if value in MEMORY_AUDIT_EVENT_TAXONOMY:
        return value
    return fallback


def normalize_audit_event_fields(payload: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    row = dict(payload or {})
    query_tokens = [
        str(item).strip()
        for item in list(row.get("query_tokens") or [])
        if item is not None and str(item).strip()
    ]
    query_paths = [
        str(item).strip()
        for item in list(row.get("query_paths") or [])
        if item is not None and str(item).strip()
    ]
    recalled_ids = [
        str(item).strip()
        for item in list(row.get("recalled_ids") or [])
        if item is not None and str(item).strip()
    ]
    blocked_reason = str(row.get("blocked_reason") or "").strip()
    outcome = str(row.get("outcome") or "").strip().lower()
    blocked = bool(row.get("blocked"))
    if blocked and not outcome:
        outcome = "blocked"
    if not outcome:
        outcome = "ok"
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_type": normalize_event_type(row.get("event_type")),
        "event_id": str(row.get("event_id") or "").strip(),
        "event_at": str(row.get("event_at") or "").strip() or _utc_now(),
        "runtime_scope": str(row.get("runtime_scope") or "project").strip() or "project",
        "thread_id": str(row.get("thread_id") or "").strip(),
        "turn_id": str(row.get("turn_id") or "").strip(),
        "memory_id": str(row.get("memory_id") or "").strip(),
        "memory_type": str(row.get("memory_type") or "").strip(),
        "query_text": str(row.get("query_text") or "").strip(),
        "query_tokens": query_tokens,
        "query_paths": query_paths,
        "query_tokens_count": len(query_tokens),
        "query_paths_count": len(query_paths),
        "candidate_count": max(0, _safe_int(row.get("candidate_count"))),
        "recalled_count": max(0, _safe_int(row.get("recalled_count"))),
        "recalled_ids": recalled_ids,
        "blocked": blocked,
        "blocked_reason": blocked_reason,
        "outcome": outcome,
        "latency_ms": max(0, _safe_int(row.get("latency_ms"))),
        "error": str(row.get("error") or "").strip(),
        "extra": dict(row.get("extra") or {}),
    }


def build_memory_audit_event(
    *,
    event_type: str,
    event_at: str | None = None,
    runtime_scope: str = "project",
    thread_id: str = "",
    turn_id: str = "",
    memory_id: str = "",
    memory_type: str = "",
    query_text: str = "",
    query_tokens: Iterable[str] | None = None,
    query_paths: Iterable[str] | None = None,
    candidate_count: int = 0,
    recalled_count: int = 0,
    recalled_ids: Iterable[str] | None = None,
    blocked: bool = False,
    blocked_reason: str = "",
    outcome: str = "",
    latency_ms: int = 0,
    error: str = "",
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return normalize_audit_event_fields(
        {
            "event_type": event_type,
            "event_at": str(event_at or "").strip() or _utc_now(),
            "runtime_scope": runtime_scope,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "memory_id": memory_id,
            "memory_type": memory_type,
            "query_text": query_text,
            "query_tokens": list(query_tokens or []),
            "query_paths": list(query_paths or []),
            "candidate_count": candidate_count,
            "recalled_count": recalled_count,
            "recalled_ids": list(recalled_ids or []),
            "blocked": blocked,
            "blocked_reason": blocked_reason,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "error": error,
            "extra": dict(extra or {}),
        }
    )


def aggregate_memory_audit_metrics(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    normalized = [normalize_audit_event_fields(item) for item in list(events or []) if isinstance(item, Mapping)]
    recall_events = [item for item in normalized if str(item.get("event_type") or "").startswith("memory_recall")]
    save_events = [item for item in normalized if str(item.get("event_type") or "").startswith("memory_save")]

    recall_attempts = len(recall_events)
    recall_blocked = sum(1 for item in recall_events if bool(item.get("blocked")) or str(item.get("outcome")) == "blocked")
    recall_candidates = sum(max(0, _safe_int(item.get("candidate_count"))) for item in recall_events)
    recall_selected = sum(max(0, _safe_int(item.get("recalled_count"))) for item in recall_events)

    save_attempts = len(save_events)
    save_accepted = sum(1 for item in save_events if str(item.get("event_type")) == "memory_save_accepted" or str(item.get("outcome")) == "accepted")
    save_blocked = sum(1 for item in save_events if bool(item.get("blocked")) or str(item.get("outcome")) == "blocked")
    save_rejected = sum(1 for item in save_events if str(item.get("event_type")) == "memory_save_rejected" or str(item.get("outcome")) == "rejected")

    pollution_signals = save_rejected + save_blocked
    latency_values = [
        _safe_float(item.get("latency_ms"), default=0.0)
        for item in normalized
        if _safe_float(item.get("latency_ms"), default=0.0) > 0
    ]

    return {
        "event_count": len(normalized),
        "recall_attempts": recall_attempts,
        "save_attempts": save_attempts,
        "blocked_events": sum(1 for item in normalized if bool(item.get("blocked")) or str(item.get("outcome")) == "blocked"),
        "recall_precision_proxy": _ratio(float(recall_selected), float(recall_candidates)),
        "save_acceptance": _ratio(float(save_accepted), float(save_attempts)),
        "pollution_proxy": _ratio(float(pollution_signals), float(save_attempts)),
        "recall_block_rate": _ratio(float(recall_blocked), float(recall_attempts)),
        "save_block_rate": _ratio(float(save_blocked), float(save_attempts)),
        "overall_block_rate": _ratio(
            float(sum(1 for item in normalized if bool(item.get("blocked")) or str(item.get("outcome")) == "blocked")),
            float(len(normalized)),
        ),
        "latency_ms_avg": (sum(latency_values) / len(latency_values)) if latency_values else 0.0,
        "latency_ms_p95": _percentile(latency_values, 95.0),
        "counts": {
            "recall_candidates": recall_candidates,
            "recall_selected": recall_selected,
            "save_accepted": save_accepted,
            "save_rejected": save_rejected,
            "save_blocked": save_blocked,
        },
    }
