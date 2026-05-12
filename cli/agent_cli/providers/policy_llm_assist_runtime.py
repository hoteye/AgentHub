from __future__ import annotations

import re
from typing import Any, Dict, List


def merge_policy_queries(*query_sets: List[str], limit: int = 4) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for query_set in query_sets:
        for item in list(query_set or []):
            query = re.sub(r"\s+", " ", str(item or "")).strip()
            if len(query) < 2 or len(query) > 40 or query in seen:
                continue
            seen.add(query)
            merged.append(query)
            if len(merged) >= limit:
                return merged
    return merged[:limit]


def policy_list_values(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def policy_normalize_list(
    value: Any,
    *,
    limit: int | None = None,
    max_len: int = 120,
) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for item in policy_list_values(value):
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if not text:
            continue
        if len(text) > max_len:
            text = text[:max_len].rstrip(" ,;；，。")
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
        if limit is not None and len(normalized) >= limit:
            break
    return normalized


def policy_result_metadata(
    *,
    fallback_used: bool,
    fallback_reason: str = "",
    result_state: str = "",
    quality_state: str = "",
) -> Dict[str, Any]:
    return {
        "fallback_used": bool(fallback_used),
        "fallback_reason": str(fallback_reason or "").strip(),
        "result_state": str(result_state or "").strip(),
        "quality_state": str(quality_state or "").strip(),
    }


def policy_has_content(payload: Dict[str, Any], *, keys: List[str]) -> bool:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list) and any(str(item or "").strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def policy_issue_hints(user_text: str) -> Dict[str, List[str]]:
    text = re.sub(r"\s+", "", str(user_text or "")).strip()
    text_lower = text.lower()
    issue_labels: List[str] = []
    must_terms: List[str] = []
    role_terms: List[str] = []

    if any(marker in text for marker in ("权限", "授权", "职责", "权责")):
        issue_labels.append("access_control")
        must_terms.extend(["权限", "职责"])
        if any(marker in text for marker in ("不匹配", "不符", "越权")):
            must_terms.extend(["最小授权", "最小必要权限", "工作职责", "工作需要"])

    if "外包" in text and any(marker in text for marker in ("季度", "报送", "统计", "清单")):
        issue_labels.append("outsourcing_reporting")
        must_terms.extend(["外包活动清单", "驻场外包人员信息统计表", "每季度末月25日前"])
        role_terms.append("金融科技部")

    if any(marker in text_lower for marker in ("ukey",)) or any(
        marker in text for marker in ("访问凭证", "数字证书", "私钥", "借予他人使用", "转授")
    ):
        issue_labels.append("credential_control")
        must_terms.extend(["访问凭证", "数字证书", "私钥", "不得借予他人使用", "不得转授"])
        role_terms.extend(["本人", "责任人"])

    if "尽职调查" in text or ("外包服务提供商" in text and "调查" in text):
        issue_labels.append("vendor_due_diligence")
        must_terms.extend(["外包服务提供商", "尽职调查", "财务情况", "风险管理", "业务连续性"])

    return {
        "issue_labels": policy_normalize_list(issue_labels, limit=4, max_len=48),
        "must_terms": policy_normalize_list(must_terms, limit=6, max_len=48),
        "role_terms": policy_normalize_list(role_terms, limit=4, max_len=48),
    }


def policy_compact_user_query(user_text: str) -> str:
    text = str(user_text or "")
    if not text.strip():
        return ""
    compact = re.sub(
        r"(请说明|请问|制度|应检索哪些|应检索|有哪些|明确要求|是否要求|如何要求|是否覆盖|有哪些明确要求)",
        " ",
        text,
    )
    compact = re.sub(r"[“”\"'：:，,。！？?（）()]", " ", compact)
    compact = re.sub(r"\s+", " ", compact).strip()
    return compact[:40].strip()


def policy_rewrite_fallback_payload(user_text: str, heuristic_queries: List[str]) -> Dict[str, Any]:
    hints = policy_issue_hints(user_text)
    must_terms = list(hints.get("must_terms") or [])
    role_terms = list(hints.get("role_terms") or [])
    seed_queries: List[str] = []
    compact_query = policy_compact_user_query(user_text)
    if compact_query:
        seed_queries.append(compact_query)
    if len(must_terms) >= 2:
        seed_queries.append(" ".join(must_terms[:2]))
    if len(must_terms) >= 4:
        seed_queries.append(" ".join(must_terms[2:4]))
    if must_terms and role_terms:
        seed_queries.append(" ".join([role_terms[0], *must_terms[:2]]))
    queries = merge_policy_queries(seed_queries, list(heuristic_queries or []), limit=4)
    return {
        "queries": queries,
        "issue_labels": list(hints.get("issue_labels") or []),
        "must_terms": must_terms[:6],
        "role_terms": role_terms[:4],
    }


def policy_rerank_fallback_payload(user_text: str, candidate_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    hints = policy_issue_hints(user_text)
    focus_terms = list(hints.get("must_terms") or [])[:4]
    ranked: List[Dict[str, Any]] = []
    for item in list(candidate_items or []):
        group = str(item.get("doc_group") or "supporting_reference").strip()
        authority_rank = int(item.get("authority_rank") or 0)
        query_term_hits = int(item.get("query_term_hits") or 0)
        haystack = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("source_name") or ""),
                str(item.get("excerpt") or ""),
            ]
        ).lower()
        focus_hits = sum(1 for term in focus_terms if str(term or "").lower() in haystack)
        group_bonus = {"governance_base": 28, "direct_rule": 24, "supporting_reference": 10}.get(group, 0)
        relevance = 30 + query_term_hits * 12 + authority_rank // 3 + focus_hits * 8 + group_bonus
        basis_type = "supporting_reference"
        if group in {"governance_base", "direct_rule"} and (query_term_hits > 0 or authority_rank >= 80 or focus_hits > 0):
            basis_type = "primary_basis"
        elif query_term_hits > 0 or focus_hits > 0 or authority_rank >= 60:
            basis_type = "scenario_basis"
        if group == "supporting_reference" and query_term_hits <= 0 and focus_hits <= 0 and authority_rank < 50:
            basis_type = "noise"
            relevance = min(relevance, 25)
        ranked.append(
            {
                "index": int(item.get("index") or 0),
                "basis_type": basis_type,
                "relevance": max(0, min(99, int(relevance))),
                "reason": (
                    f"heuristic fallback: group={group or 'unknown'}, "
                    f"authority={authority_rank}, query_hits={query_term_hits}, focus_hits={focus_hits}"
                ),
            }
        )
    ranked.sort(
        key=lambda item: (
            {"primary_basis": 0, "scenario_basis": 1, "supporting_reference": 2, "noise": 3}.get(
                str(item.get("basis_type") or ""),
                9,
            ),
            -int(item.get("relevance") or 0),
            int(item.get("index") or 0),
        )
    )
    return {
        "issue_label": str((hints.get("issue_labels") or [""])[0] or "").strip(),
        "focus_terms": focus_terms,
        "ranked": ranked[:4],
    }


def policy_normalize_basis_type(value: Any) -> str:
    basis_type = str(value or "").strip()
    if basis_type == "supplementary_reference":
        return "supporting_reference"
    return basis_type


def policy_sentences(*texts: str, limit: int = 12) -> List[str]:
    sentences: List[str] = []
    seen: set[str] = set()
    for raw_text in texts:
        for fragment in re.split(r"[。\n；;]+", str(raw_text or "")):
            sentence = re.sub(r"\s+", " ", fragment).strip(" ，,")
            if len(sentence) < 4 or sentence in seen:
                continue
            seen.add(sentence)
            sentences.append(sentence)
            if len(sentences) >= limit:
                return sentences
    return sentences


def policy_extract_fallback_payload(user_text: str, candidate_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    hints = policy_issue_hints(user_text)
    texts: List[str] = []
    for item in list(candidate_items or []):
        texts.append(str(item.get("priority_excerpt") or ""))
        texts.append(str(item.get("text") or ""))
    sentences = policy_sentences(*texts, limit=14)
    prohibitions = [
        sentence for sentence in sentences
        if any(marker in sentence for marker in ("不得", "禁止"))
    ]
    obligations = [
        sentence for sentence in sentences
        if sentence not in prohibitions
        and any(marker in sentence for marker in ("应", "应当", "需", "必须", "负责", "组织", "妥善保管", "及时交回"))
    ]
    responsibility_roles: List[str] = []
    for sentence in sentences:
        for literal in ("金融科技部", "责任人", "本人", "管理部门"):
            if literal in sentence:
                responsibility_roles.append(literal)
        role_match = re.search(r"([一-龥A-Za-z0-9]{2,16}(?:部|部门|责任人|人员|管理员|本人))", sentence)
        if role_match:
            responsibility_roles.append(role_match.group(1))
    time_requirements = [
        sentence for sentence in sentences
        if re.search(r"(每[日周月季度年]|季度末|日前|前|及时|离岗|调岗|期限|时限|频率)", sentence)
    ]
    conclusion_points = list(prohibitions[:2]) + [sentence for sentence in obligations if sentence not in prohibitions][:2]
    missing_evidence: List[str] = []
    if not conclusion_points:
        missing_evidence.append("未找到可直接引用的控制要求")
    if not responsibility_roles and any(marker in str(user_text or "") for marker in ("责任", "部门", "主体", "谁")):
        missing_evidence.append("未找到明确责任主体")
    if not time_requirements and any(marker in str(user_text or "") for marker in ("季度", "时限", "频率", "何时", "及时")):
        missing_evidence.append("未找到明确时限或频率要求")
    return {
        "issue_label": str((hints.get("issue_labels") or [""])[0] or "").strip(),
        "conclusion_points": policy_normalize_list(conclusion_points, limit=4, max_len=160),
        "obligations": policy_normalize_list(obligations, limit=4, max_len=160),
        "prohibitions": policy_normalize_list(prohibitions, limit=4, max_len=160),
        "responsibility_roles": policy_normalize_list(responsibility_roles, limit=4, max_len=48),
        "time_requirements": policy_normalize_list(time_requirements, limit=4, max_len=160),
        "missing_evidence": policy_normalize_list(missing_evidence, limit=4, max_len=80),
    }
