from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


MODE_SINGLE = "single"
MODE_ASSISTED = "assisted"
MODE_ORCHESTRATED = "orchestrated"


@dataclass(slots=True)
class ComplexityRoutingDecision:
    mode: str
    orchestration_score: int
    assisted_score: int
    reasons: list[str] = field(default_factory=list)
    policy_source: str = "rules_then_planner"

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "orchestration_score": int(self.orchestration_score),
            "assisted_score": int(self.assisted_score),
            "reasons": list(self.reasons),
            "policy_source": self.policy_source,
        }


def classify_complexity(
    user_text: str,
    *,
    has_taskbook_markdown: bool = False,
    has_checklist: bool = False,
) -> ComplexityRoutingDecision:
    text = str(user_text or "").strip().lower()
    reasons: list[str] = []
    orchestrated_score = 0
    assisted_score = 0

    def add_orchestrated(score: int, reason: str) -> None:
        nonlocal orchestrated_score
        orchestrated_score += max(0, int(score))
        reasons.append(reason)

    def add_assisted(score: int, reason: str) -> None:
        nonlocal assisted_score
        assisted_score += max(0, int(score))
        reasons.append(reason)

    if has_taskbook_markdown or has_checklist:
        add_orchestrated(4, "explicit_taskbook_or_checklist")

    if _contains_any(
        text,
        (
            "任务书",
            "taskbook",
            "任务卡",
            "task card",
            "checklist",
            "里程碑",
            "milestone",
        ),
    ):
        add_orchestrated(3, "taskbook_like_structure")

    if _contains_any(
        text,
        (
            "继续推进直到完成",
            "继续直到完成",
            "直到完成",
            "run to completion",
            "until complete",
            "do not stop",
        ),
    ):
        add_orchestrated(2, "explicit_run_to_completion")

    phase_hits = _count_contains(
        text,
        (
            "调研",
            "设计",
            "实现",
            "测试",
            "文档",
            "research",
            "design",
            "implement",
            "test",
            "documentation",
        ),
    )
    if phase_hits >= 2:
        add_orchestrated(2, "multi_phase_goal")

    if _contains_any(
        text,
        (
            "跨文件",
            "跨模块",
            "重构",
            "迁移",
            "多文件",
            "cross-file",
            "cross module",
            "refactor",
            "migration",
        ),
    ):
        add_orchestrated(2, "cross_scope_change")

    if _contains_any(
        text,
        (
            "并行",
            "后台",
            "worker",
            "background",
            "parallel",
            "delegate",
            "subagent",
            "teammate",
        ),
    ):
        add_orchestrated(2, "parallel_or_background_execution")

    if _contains_any(
        text,
        (
            "rewrite",
            "rerank",
            "extract",
            "summarize",
            "evidence",
            "摘要",
            "抽取",
            "改写",
            "重排",
        ),
    ):
        add_assisted(2, "helper_route_style_request")

    mode = MODE_SINGLE
    if orchestrated_score >= 4:
        mode = MODE_ORCHESTRATED
    elif assisted_score >= 2:
        mode = MODE_ASSISTED
    return ComplexityRoutingDecision(
        mode=mode,
        orchestration_score=orchestrated_score,
        assisted_score=assisted_score,
        reasons=reasons,
    )


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        token = str(pattern or "").strip().lower()
        if token and token in text:
            return True
    return False


def _count_contains(text: str, patterns: Iterable[str]) -> int:
    count = 0
    for pattern in patterns:
        token = str(pattern or "").strip().lower()
        if token and token in text:
            count += 1
    return count
