from __future__ import annotations

from typing import Any, Dict, List, Sequence

from plugins.psbc_policy.tools import policy_doc_read, policy_doc_search
from tools.psbc_audit_case_eval_draft_helpers import _draft_answer
from tools.psbc_audit_case_eval_model_helpers import AuditCase, _normalize_text


def _read_evidence(path: str, *, max_chars: int = 20000) -> Dict[str, Any]:
    event = policy_doc_read(path=path, max_chars=max_chars)
    payload = dict(event.payload or {})
    payload["ok"] = bool(event.ok)
    payload["summary"] = event.summary
    return payload


def _keyword_hits(text: str, keywords: Sequence[str]) -> List[str]:
    haystack = _normalize_text(text)
    hits: List[str] = []
    for keyword in keywords:
        if _normalize_text(keyword) and _normalize_text(keyword) in haystack:
            hits.append(keyword)
    return hits


def _evaluate_text(text: str, case: AuditCase) -> Dict[str, Any]:
    basis_hits = _keyword_hits(text, case.expected_basis_keywords)
    qualitative_hits = _keyword_hits(text, case.expected_qualitative_keywords)
    responsibility_hits = _keyword_hits(text, case.expected_responsibility_keywords)
    total_expected = (
        len(case.expected_basis_keywords)
        + len(case.expected_qualitative_keywords)
        + len(case.expected_responsibility_keywords)
    )
    total_hits = len(basis_hits) + len(qualitative_hits) + len(responsibility_hits)
    return {
        "basis_hits": basis_hits,
        "qualitative_hits": qualitative_hits,
        "responsibility_hits": responsibility_hits,
        "score": round(total_hits / total_expected, 4) if total_expected else 0.0,
    }


def _evaluate_live(case: AuditCase, *, draft_mode: str = "heuristic") -> Dict[str, Any]:
    search_event = policy_doc_search(query=case.live_query, limit=5)
    search_payload = dict(search_event.payload or {})
    top_docs = list(search_payload.get("documents") or [])[:5]
    top_titles = [str(item.get("title") or "") for item in top_docs]
    title_text = "\n".join(top_titles)
    title_hits = _keyword_hits(title_text, case.expected_policy_titles)

    read_payloads: List[Dict[str, Any]] = []
    for item in top_docs[:2]:
        doc_id = str(item.get("doc_id") or "").strip()
        if not doc_id:
            continue
        read_event = policy_doc_read(doc_id=doc_id, max_chars=4000)
        payload = dict(read_event.payload or {})
        payload["ok"] = bool(read_event.ok)
        payload["summary"] = read_event.summary
        if payload["ok"]:
            read_payloads.append(payload)

    drafted = _draft_answer(case, read_payloads, draft_mode=draft_mode)
    evaluation = _evaluate_text(drafted.answer["answer_text"], case)
    return {
        "query": case.live_query,
        "search_ok": bool(search_event.ok),
        "top_titles": top_titles,
        "policy_title_hits": title_hits,
        "policy_title_hit": bool(title_hits),
        "draft_mode": drafted.mode,
        "draft_fallback_reason": drafted.fallback_reason,
        "answer": drafted.answer,
        "answer_evaluation": evaluation,
    }


def _evaluate_oracle(case: AuditCase, *, draft_mode: str = "heuristic") -> Dict[str, Any]:
    evidence_docs = [_read_evidence(path) for path in case.oracle_paths]
    ok_docs = [item for item in evidence_docs if item.get("ok")]
    drafted = _draft_answer(case, ok_docs, draft_mode=draft_mode)
    evaluation = _evaluate_text(drafted.answer["answer_text"], case)
    return {
        "oracle_paths": case.oracle_paths,
        "read_ok_count": len(ok_docs),
        "draft_mode": drafted.mode,
        "draft_fallback_reason": drafted.fallback_reason,
        "answer": drafted.answer,
        "answer_evaluation": evaluation,
    }


def evaluate_case(case: AuditCase, *, draft_mode: str = "heuristic") -> Dict[str, Any]:
    return {
        "case_id": case.case_id,
        "case_name": case.case_name,
        "finding": case.finding,
        "question": case.question,
        "live": _evaluate_live(case, draft_mode=draft_mode),
        "oracle": _evaluate_oracle(case, draft_mode=draft_mode),
    }
