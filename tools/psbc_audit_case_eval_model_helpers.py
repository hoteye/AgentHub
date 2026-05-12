from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


@dataclass
class AuditCase:
    case_id: str
    case_name: str
    finding: str
    question: str
    live_query: str
    expected_policy_titles: List[str]
    oracle_paths: List[str]
    expected_basis_keywords: List[str]
    expected_qualitative_keywords: List[str]
    expected_responsibility_keywords: List[str]


@dataclass
class DraftResult:
    answer: Dict[str, Any]
    mode: str
    fallback_reason: str | None = None


def _load_cases(path: Path) -> List[AuditCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [AuditCase(**item) for item in payload]


def _normalize_text(value: str) -> str:
    text = str(value or "")
    return re.sub(r"\s+", "", text).lower()


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _split_evidence_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in str(text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) < 6:
            continue
        line = line.lstrip("#*-0123456789.（）() ")
        if len(line) < 6:
            continue
        lines.append(line)
    return _dedupe(lines)


def _query_terms(*values: str) -> List[str]:
    stop_terms = {"问题", "制度", "依据", "请给出", "针对", "以及", "和", "与", "的", "请", "给出"}
    terms: List[str] = []
    for value in values:
        source = re.sub(r"[，。；：:、（）()]", " ", str(value or ""))
        for part in source.split():
            token = part.strip()
            if len(token) < 2 or token in stop_terms:
                continue
            if token not in terms:
                terms.append(token)
    return terms[:12]


def _pick_evidence_lines(text: str, terms: Sequence[str], *, limit: int = 4) -> List[str]:
    lines = _split_evidence_lines(text)
    if not lines:
        return []
    ranked: List[tuple[int, int, int, str]] = []
    lowered_terms = [term.lower() for term in terms if term]
    priority_markers = (
        "严禁",
        "不得",
        "最小授权",
        "最小权限",
        "尽职调查",
        "每季度末月25日前",
        "信息科技外包活动清单",
        "信息科技驻场外包人员信息统计表",
        "异常处置",
        "双人复核",
        "他人UKey",
        "UKey混用",
        "外包活动统计",
    )
    for index, line in enumerate(lines):
        line_lower = line.lower()
        hit_count = sum(1 for term in lowered_terms if term in line_lower)
        if (
            hit_count <= 1
            and len(line) <= 40
            and any(marker in line for marker in ("管理规程", "管理办法", "实施细则", "操作规程"))
        ):
            continue
        if hit_count <= 0 and "应" not in line and "严禁" not in line and "负责" not in line:
            continue
        duty_bonus = 0
        if "严禁" in line:
            duty_bonus += 3
        if "应" in line:
            duty_bonus += 2
        if "负责" in line:
            duty_bonus += 1
        if any(marker in line for marker in priority_markers):
            duty_bonus += 4
        ranked.append((hit_count, duty_bonus, -index, line))
    if not ranked:
        ranked = [(0, 0, -index, line) for index, line in enumerate(lines[:limit])]
    ranked.sort(reverse=True)
    return [line for _, _, _, line in ranked[:limit]]


def _extract_responsibility_subjects(lines: Sequence[str]) -> List[str]:
    subjects: List[str] = []
    patterns = (
        r"^(.{2,40}?)(?:应|负责|需)",
        r"^(.{2,40}?)(?:至少每|严禁|原则上)",
    )
    for line in lines:
        for pattern in patterns:
            match = re.match(pattern, line)
            if not match:
                continue
            subject = match.group(1).strip("：:，, ")
            if len(subject) < 2:
                continue
            if any(
                keyword in subject
                for keyword in (
                    "部门",
                    "单位",
                    "分行",
                    "责任",
                    "运营数据中心",
                    "建设单位",
                    "业务部门",
                    "金融科技部",
                    "系统管理员",
                    "堡垒用户",
                )
            ):
                subjects.append(subject)
    return _dedupe(subjects)[:5]


def _issue_label(text: str) -> str:
    haystack = str(text or "")
    label_rules = [
        ("最小授权控制不到位", (("最小授权",), ("最小权限",), ("过度授权",), ("权责不一致",), ("工作职责", "权限"))),
        ("访问凭证借用或混用控制不到位", (("UKey", "混用"), ("UKey", "借"), ("UKey", "借用"), ("UKey", "他人使用"))),
        ("外包服务提供商尽职调查执行不到位", (("尽职调查",), ("服务提供商", "尽职调查"))),
        ("投产升级异常处置执行不到位", (("投产升级", "异常"), ("异常处置",))),
        ("投产升级双人复核和审批执行不到位", (("投产升级", "双人复核"), ("双人复核", "审批"))),
        ("外包活动和驻场人员统计报送不到位", (("驻场外包人员", "信息统计表"), ("外包活动清单",), ("季度末月25日前",))),
        ("账号和权限回收处置不到位", (("离职离岗", "变更或终止"), ("权限回收",), ("终止", "账号和权限"))),
    ]
    ranked: List[tuple[int, str]] = []
    for label, rule_groups in label_rules:
        score = 0
        for keywords in rule_groups:
            if all(keyword in haystack for keyword in keywords):
                score += len(keywords) + 1
        if score > 0:
            ranked.append((score, label))
    if ranked:
        ranked.sort(reverse=True)
        return ranked[0][1]
    return "制度执行偏差待进一步人工复核"


def _shorten(text: str, limit: int = 140) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
