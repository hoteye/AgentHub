from __future__ import annotations

import re
from typing import List

SHORT_TERM_ALLOWLIST = {"账号", "外包", "锁定", "注销", "回收", "复核", "审批", "离场", "离岗", "扣减"}
GENERIC_TERMS = {
    "原则",
    "活动",
    "服务",
    "提供",
    "使用",
    "管理",
    "办法",
    "规程",
    "细则",
    "制度",
    "要求",
    "权限",
    "银行",
    "中国",
    "邮政",
    "储蓄",
}
STOP_TERMS = {
    "什么",
    "依据",
    "制度",
    "规定",
    "问题",
    "说明",
    "存在",
    "情况",
    "用户",
    "名用户",
    "内容",
    "全文",
    "请说明",
    "给出",
    "提供",
    "列示",
    "请给出",
    "经查",
    "经统计",
    "统计发现",
    "抽查发现",
    "核查发现",
}
PHRASE_SIGNALS = (
    "投产升级异常处置",
    "投产升级",
    "异常处置",
    "升级步骤",
    "升级审批",
    "双人复核",
    "外包活动清单",
    "驻场外包人员信息统计表",
    "驻场外包人员",
    "外包活动统计",
    "外包人员信息库",
    "外包服务提供商",
    "尽职调查",
    "持续监控",
    "日常持续监控",
    "财务报表",
    "财务情况",
    "风险信息",
    "业务连续性",
    "资质能力",
    "最小授权原则",
    "最小授权",
    "最小必要权限",
    "最小权限",
    "过度授权",
    "权责不一致",
    "工作职责",
    "用户账号和权限",
    "运维安全堡垒系统",
    "堡垒用户",
    "账号删除",
    "权限回收",
    "合同期满",
    "服务质量考核",
    "服务质量评估",
    "外包服务费用",
    "合同续签",
    "ukey",
    "数字证书",
    "私钥",
    "借予他人使用",
    "转授",
)
COMPONENT_SIGNALS = (
    "数据安全",
    "长期闲置",
    "长期未登录",
    "账号",
    "权限",
    "授权",
    "锁定",
    "限制访问",
    "注销",
    "回收",
    "外包",
    "尽职调查",
    "财务状况",
    "财务情况",
    "资质能力",
    "风险管理",
    "持续监控",
    "服务质量",
    "考核",
    "费用",
    "双人复核",
    "异常处置",
    "审批",
    "审计",
    "核查",
    "离场",
    "离岗",
    "删除",
    "ukey",
)

AUDIT_BOILERPLATE_PATTERNS = (
    r"^(经查|经统计|统计发现|抽查发现|核查发现)[，,:：;；]?\s*",
    r"(请|需)(?:结合实际)?(?:说明|给出|列示|提供)(?:制度依据|依据|问题定性|责任环节|关键条款|相关条款)?",
    r"制度依据是什么",
    r"主要存在以下问题[：:]?",
    r"具体情况如下[：:]?",
)

REQUEST_PREFIX_PATTERN = re.compile(r"^(请|需)(?:结合实际)?(?:说明|给出|列示|提供|回答|分析|概括|总结)?")
REQUEST_ONLY_TERMS_PATTERN = re.compile(
    r"(制度依据|依据|问题定性|责任环节|关键条款|相关条款|主要条款|相关依据|定性|责任主体|责任部门|制度要求)"
)


def _strip_instruction_clauses(text: str) -> str:
    clauses = [part.strip() for part in re.split(r"[，,。；;！？!?]+", text) if part.strip()]
    if not clauses:
        return text
    kept: List[str] = []
    dropped_any = False
    for clause in clauses:
        probe = REQUEST_PREFIX_PATTERN.sub("", clause).strip()
        probe = REQUEST_ONLY_TERMS_PATTERN.sub(" ", probe)
        probe = re.sub(r"[和及以及、\s]+", "", probe)
        if not probe:
            dropped_any = True
            continue
        kept.append(clause)
    if kept:
        return " ".join(kept).strip()
    return "" if dropped_any else text


def normalize_policy_query_text(query: str) -> str:
    text = re.sub(r"\s+", " ", str(query or "")).strip().lower()
    if not text:
        return ""
    for pattern in AUDIT_BOILERPLATE_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"^(针对|围绕|关于|对于)\s*", " ", text)
    text = re.sub(r"[，,:：;；]\s*(请|需)(?:结合实际)?(?:说明|给出|列示|提供|回答|分析|概括|总结).*$", " ", text)
    text = _strip_instruction_clauses(text)
    text = re.sub(r"截至\d{4}年\d{1,2}月\d{1,2}日", " ", text)
    text = re.sub(r"\d+(?:个|名|次|项|家|份|个月|月|天|年|季度|人次)", " ", text)
    text = re.sub(r"[\"'“”‘’`]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ,，。；;:：")


def _keyword_pair_terms(text: str) -> List[str]:
    pairs = (
        (("账号", "权限"), "账号权限"),
        (("审计", "核查"), "审计核查"),
        (("服务质量", "考核"), "服务质量考核"),
        (("外包", "活动"), "外包活动"),
        (("外包", "人员"), "外包人员"),
        (("权限", "回收"), "权限回收"),
        (("账号", "删除"), "账号删除"),
    )
    return [label for required, label in pairs if all(term in text for term in required)]


def policy_query_terms(query: str, *, limit: int = 24) -> List[str]:
    normalized = normalize_policy_query_text(query)
    if not normalized:
        return []

    raw_terms = re.findall(r"[a-z0-9._/-]+|[\u4e00-\u9fff]{2,}", normalized)
    terms: List[str] = []
    seen: set[str] = set()

    for raw in raw_terms:
        text = raw.strip()
        text = re.sub(r"(制度依据|制度|依据|问题|情况|说明|存在|是什么|什么意思)$", "", text)
        if len(text) < 2 or re.fullmatch(r"\d+", text):
            continue

        candidates: List[str] = []
        signal_matches = [phrase for phrase in PHRASE_SIGNALS if phrase in text]
        candidates.extend(signal_matches)
        candidates.extend(marker for marker in COMPONENT_SIGNALS if marker in text)
        candidates.extend(_keyword_pair_terms(text))
        for suffix in ("管理办法", "办法", "实施细则", "细则", "管理规程", "规程", "制度", "规定", "指引", "规范"):
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                candidates.append(text[: -len(suffix)])

        keep_raw = True
        if re.fullmatch(r"[\u4e00-\u9fff]{8,}", text) and signal_matches:
            keep_raw = False
        if keep_raw:
            candidates.insert(0, text)

        for candidate in candidates:
            value = candidate.strip()
            if len(value) < 2 or value in STOP_TERMS or value in seen:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]+", value) and len(value) < 3 and value not in SHORT_TERM_ALLOWLIST:
                continue
            if value in GENERIC_TERMS and any(value != other and value in other for other in candidates):
                continue
            seen.add(value)
            terms.append(value)

    pruned: List[str] = []
    for term in terms:
        if term in GENERIC_TERMS and any(term != other and term in other for other in terms):
            continue
        if (
            len(term) <= 2
            and term not in SHORT_TERM_ALLOWLIST
            and any(term != other and term in other and len(other) >= len(term) + 2 for other in terms)
        ):
            continue
        pruned.append(term)
        if len(pruned) >= limit:
            break
    return pruned


def policy_query_compact_queries(query: str, *, limit: int = 4) -> List[str]:
    normalized = normalize_policy_query_text(query)
    if not normalized or limit <= 0:
        return []

    queries: List[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        text = re.sub(r"\s+", " ", str(candidate or "")).strip()
        if len(text) < 2 or text in seen:
            return
        seen.add(text)
        queries.append(text)

    if len(normalized) <= 24:
        _add(normalized)

    clauses = [part.strip() for part in re.split(r"[\r\n,，。；;：:（）()]+", normalized) if part.strip()]
    for clause in clauses[:4]:
        clause_terms = policy_query_terms(clause, limit=8)
        if clause_terms:
            _add(" ".join(clause_terms[:4]))
            if len(queries) >= limit:
                return queries[:limit]

    full_terms = policy_query_terms(normalized, limit=16)
    if full_terms:
        for width in (2, 3, 4):
            if len(full_terms) < width:
                continue
            for index in range(0, len(full_terms) - width + 1):
                _add(" ".join(full_terms[index : index + width]))
                if len(queries) >= limit:
                    return queries[:limit]

    if not queries:
        _add(normalized)
    return queries[:limit]
