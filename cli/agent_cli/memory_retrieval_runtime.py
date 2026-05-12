from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from cli.agent_cli import memory_projection_runtime as projection_runtime
from cli.agent_cli import memory_types


_WORD_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{1,}")


def _tokenize_text(text: str) -> List[str]:
    tokens: List[str] = []
    seen: set[str] = set()
    for match in _WORD_PATTERN.findall(str(text or "").lower()):
        token = match.strip(".,:;()[]{}<>\"'`")
        if len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def memory_query_terms(
    user_text: str,
    *,
    recent_user_messages: Iterable[str] | None = None,
) -> List[str]:
    source = [str(user_text or "")]
    source.extend(str(item or "") for item in list(recent_user_messages or []))
    return _tokenize_text("\n".join(source))


def _query_paths(query_terms: Iterable[str], *, cwd: str = "") -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for token in list(query_terms or []):
        item = str(token or "").strip().lower()
        if "/" not in item and "." not in item:
            continue
        normalized = item.lstrip("./")
        if normalized and normalized not in seen:
            seen.add(normalized)
            values.append(normalized)
    cwd_text = str(cwd or "").strip().lower().replace("\\", "/")
    if cwd_text:
        for value in cwd_text.split("/"):
            normalized = value.strip()
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            values.append(normalized)
    return values


def score_memory_candidate(
    record: Dict[str, Any],
    *,
    query_terms: Iterable[str],
    query_paths: Iterable[str],
    ranking_weights: Dict[str, Any] | None = None,
    type_weights: Dict[str, float] | None = None,
) -> Tuple[float, List[str], Dict[str, Any], Dict[str, Any]]:
    terms = [str(item or "").strip().lower() for item in list(query_terms or []) if str(item or "").strip()]
    term_set = set(terms)
    path_terms = [str(item or "").strip().lower() for item in list(query_paths or []) if str(item or "").strip()]
    ranking_contract = memory_types.normalized_ranking_weight_contract(
        ranking_weights,
        type_weights=type_weights,
    )
    component_weights = dict(ranking_contract.get("components") or {})
    weight_map = dict(ranking_contract.get("type_weights") or {})

    tags = [str(item or "").strip().lower() for item in list(record.get("tags") or []) if str(item or "").strip()]
    stored_paths = [str(item or "").strip().lower().replace("\\", "/") for item in list(record.get("paths") or []) if str(item or "").strip()]
    text_blob = "\n".join(
        [
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
            str(record.get("body") or ""),
        ]
    ).lower()
    text_tokens = set(_tokenize_text(text_blob))

    score = 0.0
    reasons: List[str] = []
    breakdown: Dict[str, Any] = {
        "components": {
            "tag": {"weight": float(component_weights.get("tag") or 0.0), "hits": [], "score": 0.0},
            "path": {"weight": float(component_weights.get("path") or 0.0), "hits": [], "score": 0.0},
            "text": {"weight": float(component_weights.get("text") or 0.0), "hits": [], "score": 0.0},
            "type": {"weight": float(component_weights.get("type") or 0.0), "kind": "", "score": 0.0},
            "salience": {"weight": float(component_weights.get("salience") or 0.0), "value": 0.0, "score": 0.0},
        },
        "total_score": 0.0,
    }

    tag_overlap = sorted(tag for tag in tags if tag in term_set)
    if tag_overlap:
        component_score = float(component_weights.get("tag") or 0.0) * float(min(len(tag_overlap), 4))
        score += component_score
        breakdown["components"]["tag"]["score"] = component_score
        breakdown["components"]["tag"]["hits"] = list(tag_overlap)
        reasons.append("tag_overlap:" + ",".join(tag_overlap[:3]))

    path_hits: List[str] = []
    for query_path in path_terms:
        for stored_path in stored_paths:
            if query_path in stored_path or stored_path in query_path:
                path_hits.append(query_path)
                break
    if path_hits:
        unique_hits = sorted(set(path_hits))
        component_score = float(component_weights.get("path") or 0.0) * float(min(len(unique_hits), 3))
        score += component_score
        breakdown["components"]["path"]["score"] = component_score
        breakdown["components"]["path"]["hits"] = list(unique_hits)
        reasons.append("path_overlap:" + ",".join(unique_hits[:3]))

    keyword_hits = sorted(term for term in term_set if term in text_tokens)
    if keyword_hits:
        component_score = float(component_weights.get("text") or 0.0) * float(min(len(keyword_hits), 5))
        score += component_score
        breakdown["components"]["text"]["score"] = component_score
        breakdown["components"]["text"]["hits"] = list(keyword_hits)
        reasons.append("keyword_overlap:" + ",".join(keyword_hits[:4]))

    memory_type = memory_types.normalize_memory_type(str(record.get("memory_type") or ""))
    type_bonus = float(component_weights.get("type") or 0.0) * float(weight_map.get(memory_type, 0.0))
    if type_bonus:
        score += type_bonus
        breakdown["components"]["type"]["score"] = type_bonus
        breakdown["components"]["type"]["kind"] = memory_type
        reasons.append(f"type_weight:{memory_type}={type_bonus:.2f}")

    try:
        salience = float(record.get("salience") or 0.0)
    except (TypeError, ValueError):
        salience = 0.0
    if salience > 0:
        salience_bonus = float(component_weights.get("salience") or 0.0) * salience
        score += salience_bonus
        breakdown["components"]["salience"]["score"] = salience_bonus
        breakdown["components"]["salience"]["value"] = salience
        reasons.append(f"salience:{salience_bonus:.2f}")

    breakdown["total_score"] = float(score)
    return score, reasons, breakdown, ranking_contract


def _sorted_scored_candidates(
    memories: Iterable[Dict[str, Any]],
    *,
    query_terms: Iterable[str],
    query_paths: Iterable[str],
    user_text: str = "",
    ranking_weights: Dict[str, Any] | None = None,
    type_weights: Dict[str, float] | None = None,
    enable_hybrid: bool = False,
    semantic_backend: Any | None = None,
) -> List[Dict[str, Any]]:
    payload = dict(ranking_weights or {})
    hybrid_payload = payload.get("hybrid") if isinstance(payload.get("hybrid"), dict) else {}
    try:
        semantic_weight = float(hybrid_payload.get("semantic", payload.get("semantic_weight", 0.0)) or 0.0)
    except (TypeError, ValueError):
        semantic_weight = 0.0
    try:
        rule_weight = float(hybrid_payload.get("rule", payload.get("rule_weight", 1.0)) or 1.0)
    except (TypeError, ValueError):
        rule_weight = 1.0

    semantic_scores: Dict[str, float] = {}
    semantic_enabled = bool(enable_hybrid and semantic_weight > 0 and callable(semantic_backend))
    if semantic_enabled:
        try:
            raw_scores = semantic_backend(
                user_text=str(user_text or ""),
                query_terms=list(query_terms or []),
                query_paths=list(query_paths or []),
                candidates=list(memories or []),
            )
        except TypeError:
            raw_scores = semantic_backend(str(user_text or ""), list(memories or []))
        except Exception:
            raw_scores = {}
        if isinstance(raw_scores, dict):
            for raw_memory_id, raw_score in raw_scores.items():
                memory_id = str(raw_memory_id or "").strip()
                if not memory_id:
                    continue
                try:
                    semantic_scores[memory_id] = float(raw_score)
                except (TypeError, ValueError):
                    continue

    scored: List[Dict[str, Any]] = []
    for record in list(memories or []):
        item = dict(record or {})
        if not item or memory_types.normalize_memory_status(str(item.get("status") or "")) != "active":
            continue
        score, reasons, score_breakdown, ranking_contract = score_memory_candidate(
            item,
            query_terms=query_terms,
            query_paths=query_paths,
            ranking_weights=ranking_weights,
            type_weights=type_weights,
        )
        memory_id = str(item.get("memory_id") or "").strip()
        semantic_score = float(semantic_scores.get(memory_id, 0.0)) if semantic_enabled else 0.0
        fusion_score = float(score)
        if semantic_enabled:
            fusion_score = (rule_weight * float(score)) + (semantic_weight * semantic_score)

        explainability = {
            "rule_score": float(score),
            "semantic_score": float(semantic_score),
            "fusion_score": float(fusion_score),
        }
        item["recall_score"] = float(fusion_score)
        item["recall_reasons"] = list(reasons)
        item["recall_score_breakdown"] = dict(score_breakdown or {})
        item["recall_ranking_contract"] = dict(ranking_contract or {})
        item["recall_explainability"] = dict(explainability)
        scored.append(item)
    scored.sort(
        key=lambda item: (
            -float(item.get("recall_score") or 0.0),
            str(item.get("updated_at") or ""),
            str(item.get("memory_id") or ""),
        )
    )
    return scored


def recall_memories_for_turn(
    memories: Iterable[Dict[str, Any]],
    *,
    user_text: str,
    recent_user_messages: Iterable[str] | None = None,
    cwd: str = "",
    limit: int = 5,
    min_score: float = 0.1,
    max_excerpt_chars: int = 600,
    max_total_chars: int = 4000,
    ranking_weights: Dict[str, Any] | None = None,
    type_weights: Dict[str, float] | None = None,
    enable_hybrid: bool = False,
    semantic_backend: Any | None = None,
) -> List[Dict[str, Any]]:
    query_terms = memory_query_terms(user_text, recent_user_messages=recent_user_messages)
    query_paths = _query_paths(query_terms, cwd=cwd)
    candidates = _sorted_scored_candidates(
        memories,
        query_terms=query_terms,
        query_paths=query_paths,
        user_text=user_text,
        ranking_weights=ranking_weights,
        type_weights=type_weights,
        enable_hybrid=enable_hybrid,
        semantic_backend=semantic_backend,
    )
    if limit <= 0:
        return []
    remaining_chars = max_total_chars if max_total_chars > 0 else 10**9
    recalled: List[Dict[str, Any]] = []
    for item in candidates:
        score = float(item.get("recall_score") or 0.0)
        if score < float(min_score):
            continue
        if len(recalled) >= limit:
            break
        excerpt = projection_runtime.memory_excerpt(item, max_chars=max_excerpt_chars)
        if remaining_chars <= 0:
            break
        if max_total_chars > 0 and len(excerpt) > remaining_chars:
            if remaining_chars <= 0:
                break
            excerpt = excerpt[:remaining_chars]
        remaining_chars -= len(excerpt)
        reasons = [str(value).strip() for value in list(item.get("recall_reasons") or []) if str(value).strip()]
        score_breakdown = dict(item.get("recall_score_breakdown") or {})
        ranking_contract = dict(item.get("recall_ranking_contract") or {})
        explainability = dict(item.get("recall_explainability") or {})
        recalled.append(
            {
                "memory": dict(item),
                "score": score,
                "reasons": reasons,
                "score_breakdown": score_breakdown,
                "ranking_contract": ranking_contract,
                "explainability": explainability,
                "excerpt": excerpt,
                "query_terms": list(query_terms),
                "query_paths": list(query_paths),
                "reference_context_item": projection_runtime.recalled_memory_reference_context_item(
                    item,
                    score=score,
                    reasons=reasons,
                    excerpt=excerpt,
                    score_breakdown=score_breakdown,
                    ranking_contract=ranking_contract,
                    explainability=explainability,
                ),
            }
        )
    return recalled
