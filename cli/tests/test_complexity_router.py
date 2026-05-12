from __future__ import annotations

from cli.agent_cli.orchestration.complexity_router import (
    MODE_ASSISTED,
    MODE_ORCHESTRATED,
    MODE_SINGLE,
    classify_complexity,
)


def test_classify_complexity_marks_orchestrated_for_taskbook_style_long_task() -> None:
    decision = classify_complexity(
        "请按任务书继续推进直到完成，做跨文件重构，后台并行执行并验收下一卡。",
        has_taskbook_markdown=True,
    )

    assert decision.mode == MODE_ORCHESTRATED
    assert decision.orchestration_score >= 4
    assert "explicit_taskbook_or_checklist" in decision.reasons


def test_classify_complexity_marks_orchestrated_for_explicit_taskbook_markdown() -> None:
    decision = classify_complexity(
        "# Taskbook\n\n### CARD-001: Research\n- goal: research workflow\n- owned_files: docs/research.md\n- acceptance_criteria: capture findings",
        has_taskbook_markdown=True,
    )

    assert decision.mode == MODE_ORCHESTRATED
    assert decision.orchestration_score >= 4


def test_classify_complexity_marks_assisted_for_helper_route_style_request() -> None:
    decision = classify_complexity("请先 rewrite 然后 rerank evidence 并做 extract 摘要。")

    assert decision.mode == MODE_ASSISTED
    assert decision.assisted_score >= 2
    assert "helper_route_style_request" in decision.reasons


def test_classify_complexity_defaults_to_single_for_small_local_task() -> None:
    decision = classify_complexity("修一个小 bug，改一处文案。")

    assert decision.mode == MODE_SINGLE
    assert decision.orchestration_score < 4
    assert decision.assisted_score < 2
