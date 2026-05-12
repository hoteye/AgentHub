from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Iterable, List, Tuple

from cli.agent_cli.memory_events import (
    aggregate_memory_audit_metrics,
    build_memory_audit_event,
)
from cli.agent_cli.memory_retrieval_runtime import recall_memories_for_turn
from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli.models import ReferenceContextItem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_memory_store(runtime: Any) -> Any:
    store = getattr(runtime, "_memory_store", None)
    if store is not None and callable(getattr(store, "list_memories", None)):
        return store
    store = MemoryStore.default()
    setattr(runtime, "_memory_store", store)
    return store


def _runtime_memory_context_limit(runtime: Any) -> int:
    value = getattr(runtime, "_memory_context_limit", None)
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 3
    return max(1, min(limit, 20))


def _recent_user_messages(runtime: Any, *, limit: int = 3) -> List[str]:
    messages: List[str] = []
    for item in list(getattr(runtime, "_base_history", []) or [])[::-1]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        text = str(item.get("content") or "").strip()
        if text:
            messages.append(text)
        if len(messages) >= limit:
            break
    if len(messages) < limit:
        for item in list(getattr(runtime, "history_turns", []) or [])[::-1]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("user_text") or "").strip()
            if text:
                messages.append(text)
            if len(messages) >= limit:
                break
    messages.reverse()
    return messages


def _current_user_query(recent_user_messages: Iterable[str]) -> str:
    items = [str(item or "").strip() for item in list(recent_user_messages or []) if str(item or "").strip()]
    return items[-1] if items else ""


def memory_context_turn_update(
    runtime: Any,
) -> Tuple[List[Dict[str, str]], List[ReferenceContextItem], Dict[str, Any]]:
    started_at = perf_counter()
    store = _runtime_memory_store(runtime)
    limit = _runtime_memory_context_limit(runtime)
    blocked_reason = ""
    recall_error = ""
    try:
        memories = list(store.list_memories(limit=200, status="active"))
    except Exception as exc:
        memories = []
        blocked_reason = "memory_store_unavailable"
        recall_error = str(exc)
    recent_user_messages = _recent_user_messages(runtime)
    user_text = _current_user_query(recent_user_messages)
    recalled: List[Dict[str, Any]] = []
    if not blocked_reason and not memories:
        blocked_reason = "no_active_memories"
    elif not blocked_reason and not user_text:
        blocked_reason = "empty_query"
    if not blocked_reason:
        try:
            recalled = recall_memories_for_turn(
                memories,
                user_text=user_text,
                recent_user_messages=recent_user_messages[:-1],
                cwd=str(getattr(runtime, "cwd", "") or ""),
                limit=limit,
            )
        except Exception as exc:
            recalled = []
            blocked_reason = "recall_error"
            recall_error = str(exc)
    if not blocked_reason and not recalled:
        blocked_reason = "no_recall_match"
    context_items: List[ReferenceContextItem] = []
    recalled_ids: List[str] = []
    total_chars = 0
    query_tokens: List[str] = []
    query_paths: List[str] = []
    ranking_explainability: List[Dict[str, Any]] = []
    if recalled:
        query_tokens = [
            str(item).strip()
            for item in list(recalled[0].get("query_terms") or [])
            if str(item).strip()
        ]
        query_paths = [
            str(item).strip()
            for item in list(recalled[0].get("query_paths") or [])
            if str(item).strip()
        ]
    for index, item in enumerate(recalled, start=1):
        payload = item.get("reference_context_item")
        if isinstance(payload, dict):
            context_items.append(ReferenceContextItem.from_dict(payload))
        memory = dict(item.get("memory") or {})
        memory_id = str(memory.get("memory_id") or "").strip()
        memory_type = str(memory.get("memory_type") or "").strip()
        score = float(item.get("score") or 0.0)
        reasons = [str(value).strip() for value in list(item.get("reasons") or []) if str(value).strip()]
        excerpt = str(item.get("excerpt") or "")
        if memory_id:
            recalled_ids.append(memory_id)
            try:
                store.record_memory_hit(memory_id)
            except Exception:
                pass
        total_chars += len(excerpt)
        ranking_explainability.append(
            {
                "rank": index,
                "memory_id": memory_id,
                "memory_type": memory_type,
                "score": score,
                "reasons": reasons,
                "excerpt_chars": len(excerpt),
                "selected": True,
            }
        )
    recalled_types = sorted(
        {
            str(item.get("memory_type") or "").strip()
            for item in ranking_explainability
            if str(item.get("memory_type") or "").strip()
        }
    )
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    audit_event = build_memory_audit_event(
        event_type="memory_recall_blocked" if blocked_reason else "memory_recall_evaluated",
        event_at=_utc_now(),
        runtime_scope=str(getattr(store, "scope", "project") or "project"),
        thread_id=str(getattr(runtime, "thread_id", "") or ""),
        memory_type=recalled_types[0] if len(recalled_types) == 1 else "",
        query_text=user_text,
        query_tokens=query_tokens,
        query_paths=query_paths,
        candidate_count=len(recalled),
        recalled_count=len(context_items),
        recalled_ids=recalled_ids,
        blocked=bool(blocked_reason),
        blocked_reason=blocked_reason,
        outcome="blocked" if blocked_reason else "ok",
        latency_ms=elapsed_ms,
        error=recall_error,
        extra={
            "store_memory_count": len(memories),
            "ranking_count": len(ranking_explainability),
        },
    )
    metrics_baseline = aggregate_memory_audit_metrics([audit_event])
    snapshot = {
        "query_text": user_text,
        "query_tokens": query_tokens,
        "query_paths": query_paths,
        "recalled_count": len(context_items),
        "recalled_ids": recalled_ids,
        "recalled_types": recalled_types,
        "total_chars": total_chars,
        "generated_at": _utc_now(),
        "limit": limit,
        "store_memory_count": len(memories),
        "candidate_count": len(recalled),
        "blocked": bool(blocked_reason),
        "blocked_reason": blocked_reason,
        "recall_error": recall_error,
        "ranking_explainability": ranking_explainability,
        "recall_latency_ms": elapsed_ms,
        "audit_events": [audit_event],
        "metrics_baseline": metrics_baseline,
        "snapshot_version": "v1",
    }
    return [], context_items, snapshot
