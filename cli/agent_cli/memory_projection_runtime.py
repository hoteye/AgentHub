from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli import memory_types


def memory_excerpt(record: Dict[str, Any], *, max_chars: int) -> str:
    summary = str(record.get("summary") or "").strip()
    body = str(record.get("body") or "").strip()
    if summary and body:
        text = f"{summary}\n\n{body}"
    else:
        text = summary or body
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars]
    return text


def recalled_memory_reference_context_item(
    record: Dict[str, Any],
    *,
    score: float,
    reasons: List[str],
    excerpt: str,
    score_breakdown: Dict[str, Any] | None = None,
    ranking_contract: Dict[str, Any] | None = None,
    explainability: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    memory_id = str(record.get("memory_id") or "").strip()
    memory_type = memory_types.normalize_memory_type(str(record.get("memory_type") or ""))
    summary = str(record.get("summary") or "").strip()
    title = str(record.get("title") or "").strip()
    label = f"{memory_type}_memory"
    return {
        "item_type": "memory",
        "source": "runtime:memory_store",
        "label": label,
        "path": f"memory://{memory_id}" if memory_id else "",
        "description": "recalled by relevance",
        "metadata": {
            "memory_id": memory_id,
            "memory_type": memory_type,
            "title": title,
            "summary": summary,
            "score": float(score),
            "score_breakdown": dict(score_breakdown or {}),
            "ranking_contract": dict(ranking_contract or {}),
            "explainability": dict(explainability or {}),
            "reasons": [str(item).strip() for item in list(reasons or []) if str(item).strip()],
            "excerpt": str(excerpt or "").strip(),
            "tags": memory_types.normalize_string_list(list(record.get("tags") or [])),
            "paths": memory_types.normalize_string_list(list(record.get("paths") or [])),
        },
    }


def memory_candidate_preview(candidate: Dict[str, Any], *, max_chars: int = 800) -> Dict[str, Any]:
    payload = dict(candidate or {})
    body = str(payload.get("body") or "").strip()
    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars]
    return {
        "memory_type": memory_types.normalize_memory_type(str(payload.get("memory_type") or "")),
        "title": str(payload.get("title") or "").strip(),
        "summary": str(payload.get("summary") or "").strip(),
        "body": body,
        "tags": memory_types.normalize_string_list(list(payload.get("tags") or [])),
        "paths": memory_types.normalize_string_list(list(payload.get("paths") or [])),
        "reasons": memory_types.normalize_string_list(list(payload.get("reasons") or [])),
        "blocked": bool(payload.get("blocked")),
        "blocked_reason": str(payload.get("blocked_reason") or "").strip(),
    }
