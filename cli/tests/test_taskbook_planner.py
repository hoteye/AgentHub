from __future__ import annotations

import pytest

from cli.agent_cli.orchestration.taskbook_planner import plan_taskbook_from_text
from cli.agent_cli.orchestration.taskbook_state import (
    TaskCardDependencyStatus,
    TaskCardStatus,
)


def test_plan_taskbook_from_markdown_builds_snapshot_cards_and_states() -> None:
    markdown = """
# 多模型复杂任务

### CARD-001: 冻结 schema
- goal: 完成 runtime schema 定义
- owned_files: cli/agent_cli/orchestration/taskbook_models.py, cli/agent_cli/orchestration/taskbook_state.py
- acceptance_criteria: schema round-trip 测试通过

### CARD-002: 接 storage
- goal: 接入文件层持久化
- owned_files: cli/agent_cli/orchestration/taskbook_storage.py
- depends_on: CARD-001
- acceptance_criteria: run/card 可读写
- execution_mode: background teammate
"""
    plan = plan_taskbook_from_text(run_id="ctrun_demo", source_text=markdown, version=1)

    assert plan.source == "markdown"
    assert plan.snapshot.run_id == "ctrun_demo"
    assert len(plan.cards) == 2
    assert plan.snapshot.cards == ["CARD-001", "CARD-002"]
    assert plan.cards[0].owned_files
    assert plan.cards[1].depends_on == ["CARD-001"]
    assert plan.cards[1].execution_mode == "background_teammate"
    assert len(plan.states) == 2
    assert plan.states[0].status == TaskCardStatus.DRAFT
    assert plan.states[0].dependency_status == TaskCardDependencyStatus.SATISFIED
    assert plan.states[1].dependency_status == TaskCardDependencyStatus.PENDING


def test_plan_taskbook_from_plain_text_builds_single_card_when_fields_present() -> None:
    text = """
实现复杂任务 intake 最小版
owned_files: cli/agent_cli/orchestration/taskbook_planner.py; cli/tests/test_taskbook_planner.py
acceptance_criteria: planner 生成 taskbook snapshot; 缺失字段会报错
depends_on: CARD-000
"""
    plan = plan_taskbook_from_text(run_id="ctrun_plain", source_text=text, version=1)

    assert plan.source == "task_text"
    assert len(plan.cards) == 1
    assert plan.cards[0].owned_files == [
        "cli/agent_cli/orchestration/taskbook_planner.py",
        "cli/tests/test_taskbook_planner.py",
    ]
    assert plan.cards[0].acceptance_criteria == ["planner 生成 taskbook snapshot", "缺失字段会报错"]
    assert plan.cards[0].depends_on == ["CARD-000"]


def test_plan_taskbook_rejects_missing_owned_scope() -> None:
    markdown = """
# 缺少 owned scope

### CARD-001: only acceptance
- acceptance_criteria: should fail
"""
    with pytest.raises(ValueError, match="missing owned scope"):
        plan_taskbook_from_text(run_id="ctrun_bad", source_text=markdown)


def test_plan_taskbook_relaxed_markdown_backfills_missing_scope_and_acceptance() -> None:
    markdown = """
# 阶段型纲要

### CARD-001: 探测 provider
- goal: 补 provider availability 探测

### CARD-002: 接确认流
- goal: 编排入口接到 TUI/host 确认流
"""
    plan = plan_taskbook_from_text(
        run_id="ctrun_relaxed",
        source_text=markdown,
        relaxed_markdown=True,
    )

    assert len(plan.cards) == 2
    assert plan.cards[0].owned_files == ["<scope-to-confirm>"]
    assert plan.cards[0].acceptance_criteria
    assert "Refine owned_files" in plan.cards[0].acceptance_criteria[1]
    assert plan.cards[1].owned_files == ["<scope-to-confirm>"]
    assert plan.cards[1].acceptance_criteria


def test_plan_taskbook_rejects_missing_acceptance_criteria() -> None:
    markdown = """
# 缺少 acceptance

### CARD-001: only owned files
- owned_files: cli/agent_cli/orchestration/taskbook_planner.py
"""
    with pytest.raises(ValueError, match="missing acceptance criteria"):
        plan_taskbook_from_text(run_id="ctrun_bad2", source_text=markdown)


def test_plan_taskbook_does_not_misclassify_dispatch_path_as_patch_mutation() -> None:
    markdown = """
# dispatch path should stay read-only

### CARD-001: Research command behavior
- goal: research current command behavior and summarize findings
- owned_files: docs/research_dispatch.md
- acceptance_criteria: capture findings for the command behavior
"""
    plan = plan_taskbook_from_text(run_id="ctrun_dispatch_path", source_text=markdown)

    assert plan.cards[0].kind.value == "read_only"


def test_plan_taskbook_plain_text_background_teammate_update_is_workspace_mutating() -> None:
    text = """
background teammate update orchestration status rendering
owned_files: cli/agent_cli/runtime_core/orchestration_commands.py
acceptance_criteria: runtime wiring updated
"""
    plan = plan_taskbook_from_text(run_id="ctrun_plain_bg_teammate", source_text=text, version=1)

    assert len(plan.cards) == 1
    assert plan.cards[0].kind.value == "workspace_mutating"
    assert plan.cards[0].execution_mode.value == "background_teammate"


def test_plan_taskbook_plain_text_free_form_without_structured_fields_uses_safe_defaults() -> None:
    text = "我想处理当前大文件拆解任务，请先给我任务书预览。"

    plan = plan_taskbook_from_text(run_id="ctrun_plain_freeform", source_text=text, version=1)

    assert len(plan.cards) == 1
    assert plan.cards[0].owned_files == ["<scope-to-confirm>"]
    assert plan.cards[0].acceptance_criteria
    assert "Refine owned_files" in plan.cards[0].acceptance_criteria[1]


def test_plan_taskbook_plain_text_free_form_extracts_file_scope_candidates() -> None:
    text = "拆分 policy_grounding.py，并补 cli/tests/test_taskbook_planner.py 的回归覆盖。"

    plan = plan_taskbook_from_text(run_id="ctrun_plain_scope_extract", source_text=text, version=1)

    assert len(plan.cards) == 1
    assert plan.cards[0].owned_files == [
        "policy_grounding.py",
        "cli/tests/test_taskbook_planner.py",
    ]
    assert plan.cards[0].kind.value == "workspace_mutating"


def test_plan_taskbook_respects_explicit_visible_child_tab_execution_mode() -> None:
    markdown = """
# visible child tab orchestration

### CARD-001: Read-only child task
- goal: read-only inspect one file
- owned_files: docs/one.md
- acceptance_criteria: findings reported
- execution_mode: visible_child_tab
"""

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child", source_text=markdown)

    assert plan.cards[0].kind.value == "read_only"
    assert plan.cards[0].execution_mode.value == "visible_child_tab"


def test_plan_taskbook_markdown_summarize_visible_child_cards_are_read_only() -> None:
    markdown = """
# visible child tab orchestration

### CARD-001: README child
- goal: read README and summarize AgentHub project capability
- owned_files: README.md
- acceptance_criteria: README summary reported
- execution_mode: visible_child_tab

### CARD-002: Docs child
- goal: read docs and summarize tab orchestration capability
- owned_files: docs
- acceptance_criteria: docs summary reported
- execution_mode: visible_child_tab
"""

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child_summarize", source_text=markdown)

    assert [card.kind.value for card in plan.cards] == ["read_only", "read_only"]
    assert [card.execution_mode.value for card in plan.cards] == [
        "visible_child_tab",
        "visible_child_tab",
    ]
    assert [card.can_run_in_parallel for card in plan.cards] == [True, True]


def test_plan_taskbook_plain_text_visible_child_request_splits_named_child_tabs() -> None:
    text = "请把当前项目能力调研拆给两个可见子tab并汇总：一个看README，一个看docs。"

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child_plain", source_text=text)

    assert plan.source == "task_text"
    assert len(plan.cards) == 2
    assert [card.card_id for card in plan.cards] == ["CARD-001", "CARD-002"]
    assert [card.execution_mode.value for card in plan.cards] == [
        "visible_child_tab",
        "visible_child_tab",
    ]
    assert [card.kind.value for card in plan.cards] == ["read_only", "read_only"]
    assert plan.cards[0].owned_files == ["README"]
    assert plan.cards[1].owned_files == ["docs"]
    assert plan.cards[0].executor_role.value == "scout"


def test_plan_taskbook_plain_text_visible_child_request_splits_when_child_tab_phrase_wraps() -> (
    None
):
    text = "请把当前项目能力调研拆给两个可见子\n    tab并汇总：一个看README，一个看docs。"

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child_wrapped_phrase", source_text=text)

    assert len(plan.cards) == 2
    assert [card.execution_mode.value for card in plan.cards] == [
        "visible_child_tab",
        "visible_child_tab",
    ]
    assert [card.owned_files for card in plan.cards] == [["README"], ["docs"]]


def test_plan_taskbook_plain_text_visible_child_request_splits_multiple_scope_mentions() -> None:
    text = "请并发分派可见子tab查看 README、docs 和 pyproject.toml，然后汇总项目能力。"

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child_scopes", source_text=text)

    assert len(plan.cards) == 3
    assert [card.execution_mode.value for card in plan.cards] == [
        "visible_child_tab",
        "visible_child_tab",
        "visible_child_tab",
    ]
    assert [card.owned_files[0] for card in plan.cards] == ["README", "docs", "pyproject.toml"]
    assert [card.title for card in plan.cards] == [
        "Read README",
        "Read docs",
        "Read pyproject.toml",
    ]


def test_plan_taskbook_plain_text_visible_child_request_keeps_single_card_without_multiple_scopes() -> (
    None
):
    text = "请用可见子tab查看 README 并总结。"

    plan = plan_taskbook_from_text(run_id="ctrun_visible_child_single_scope", source_text=text)

    assert len(plan.cards) == 1
