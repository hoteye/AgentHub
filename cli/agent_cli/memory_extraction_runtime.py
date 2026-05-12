from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from cli.agent_cli import memory_types


_SENSITIVE_PATTERNS = (
    re.compile(r"\b(token|secret|password|passwd|api[_-]?key|cookie)\b", flags=re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9]{10,})\b"),
)


def contains_sensitive_content(text: str) -> bool:
    source = str(text or "")
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(source):
            return True
    return False


def candidate_decision_contract(candidate: Dict[str, Any]) -> tuple[str, str]:
    payload = dict(candidate or {})
    blocked_sensitive = bool(payload.get("blocked_sensitive"))
    blocked_reason = str(payload.get("blocked_reason") or "").strip()
    if blocked_sensitive or blocked_reason:
        return (
            "block",
            memory_types.normalize_candidate_decision_reason(
                blocked_reason or "contains_sensitive_content"
            ),
        )

    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    if len(title) + len(summary) < 24:
        return ("review", "low_signal_short_content")
    return ("safe", "eligible_auto_writeback")


def normalize_memory_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(candidate or {})
    memory_type = memory_types.normalize_memory_type(str(payload.get("memory_type") or "project"))
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    body = str(payload.get("body") or "").strip()
    tags = memory_types.normalize_string_list(list(payload.get("tags") or []))
    paths = memory_types.normalize_string_list(list(payload.get("paths") or []))
    reasons = memory_types.normalize_string_list(list(payload.get("reasons") or []))
    blocked_reason = str(payload.get("blocked_reason") or "").strip()
    decision, decision_reason = candidate_decision_contract(
        {
            "title": title,
            "summary": summary,
            "blocked_sensitive": bool(payload.get("blocked_sensitive")),
            "blocked_reason": blocked_reason,
        }
    )
    return {
        "memory_type": memory_type,
        "title": title,
        "summary": summary,
        "body": body,
        "tags": tags,
        "paths": paths,
        "reasons": reasons,
        "blocked_sensitive": bool(payload.get("blocked_sensitive")),
        "blocked_reason": blocked_reason,
        "decision": memory_types.normalize_candidate_decision(str(payload.get("decision") or decision)),
        "decision_reason": memory_types.normalize_candidate_decision_reason(
            str(payload.get("decision_reason") or decision_reason)
        ),
        "source": str(payload.get("source") or "last_turn").strip() or "last_turn",
    }


def preview_payload_from_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_memory_candidate(candidate)
    return {
        "memory_type": normalized.get("memory_type") or "project",
        "title": normalized.get("title") or "",
        "summary": normalized.get("summary") or "",
        "paths": list(normalized.get("paths") or []),
        "tags": list(normalized.get("tags") or []),
        "reasons": list(normalized.get("reasons") or []),
        "blocked_sensitive": bool(normalized.get("blocked_sensitive")),
        "blocked_reason": str(normalized.get("blocked_reason") or "").strip(),
        "source": str(normalized.get("source") or "last_turn").strip() or "last_turn",
    }


def dedupe_memory_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in list(candidates or []):
        normalized = normalize_memory_candidate(raw)
        key = (
            str(normalized.get("memory_type") or ""),
            str(normalized.get("title") or "").lower(),
            str(normalized.get("summary") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _candidate_from_text(
    *,
    user_text: str,
    assistant_text: str,
    memory_type: str,
    paths: Iterable[str] | None = None,
) -> Dict[str, Any]:
    title = str(user_text or "").strip()[:80] or str(assistant_text or "").strip()[:80] or "memory_candidate"
    summary = str(assistant_text or "").strip()[:600] or str(user_text or "").strip()[:600]
    body_lines = [
        "source=last_turn_preview",
        f"user={str(user_text or '').strip() or '-'}",
        f"assistant={str(assistant_text or '').strip() or '-'}",
    ]
    combined = "\n".join(body_lines)
    blocked_sensitive = contains_sensitive_content(user_text) or contains_sensitive_content(assistant_text)
    blocked_reason = "contains_sensitive_content" if blocked_sensitive else ""
    reasons = ["from_last_turn", "non_derivable_candidate"]
    if blocked_sensitive:
        reasons.append("blocked_sensitive")
        reasons.append("blocked_sensitive_content")
    return normalize_memory_candidate(
        {
            "memory_type": memory_type,
            "title": title,
            "summary": summary,
            "body": combined,
            "tags": ["preview", "last_turn"],
            "paths": list(paths or []),
            "reasons": reasons,
            "blocked_sensitive": blocked_sensitive,
            "blocked_reason": blocked_reason,
        }
    )


def extract_memory_candidates_from_last_turn(
    *,
    turn: Dict[str, Any] | None,
    memory_type: str = "project",
    paths: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    payload = dict(turn or {})
    if not payload:
        return []
    user_text = str(payload.get("user_text") or "").strip()
    assistant_text = str(payload.get("assistant_history_text") or payload.get("assistant_text") or "").strip()
    if not user_text and not assistant_text:
        return []
    candidate = _candidate_from_text(
        user_text=user_text,
        assistant_text=assistant_text,
        memory_type=memory_type,
        paths=paths,
    )
    return dedupe_memory_candidates([candidate])
