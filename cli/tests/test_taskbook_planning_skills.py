from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_planning_skills import (
    VisibleChildTabPlanningSkill,
    plan_plain_text_with_builtin_skills,
)


def test_visible_child_tab_planning_skill_splits_named_child_tabs() -> None:
    skill = VisibleChildTabPlanningSkill()

    drafts = skill.plan(
        "请把当前项目能力调研拆给两个可见子tab并汇总：一个看README，一个看docs。",
        objective="项目能力调研",
    )

    assert len(drafts) == 2
    assert [draft.execution_mode for draft in drafts] == [
        "visible_child_tab",
        "visible_child_tab",
    ]
    assert [draft.owned_files for draft in drafts] == [["README"], ["docs"]]
    assert [draft.executor_role for draft in drafts] == ["scout", "scout"]


def test_builtin_plain_text_planning_skills_return_first_matching_skill_result() -> None:
    drafts = plan_plain_text_with_builtin_skills(
        "请并发分派可见子tab查看 README、docs 和 pyproject.toml，然后汇总项目能力。",
        objective="项目能力调研",
    )

    assert len(drafts) == 3
    assert [draft.card_id for draft in drafts] == ["CARD-001", "CARD-002", "CARD-003"]
    assert [draft.title for draft in drafts] == [
        "Read README",
        "Read docs",
        "Read pyproject.toml",
    ]
    assert [draft.owned_files[0] for draft in drafts] == ["README", "docs", "pyproject.toml"]


def test_builtin_plain_text_planning_skills_decline_single_visible_child_scope() -> None:
    drafts = plan_plain_text_with_builtin_skills(
        "请用可见子tab查看 README 并总结。",
        objective="查看 README",
    )

    assert drafts == []


def test_builtin_plain_text_planning_skills_tolerate_wrapped_child_tab_phrase() -> None:
    drafts = plan_plain_text_with_builtin_skills(
        "请把当前项目能力调研拆给两个可见子\n    tab并汇总：一个看README，一个看docs。",
        objective="项目能力调研",
    )

    assert len(drafts) == 2
    assert [draft.owned_files for draft in drafts] == [["README"], ["docs"]]
