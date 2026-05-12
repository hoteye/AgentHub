from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cli.agent_cli.orchestration import taskbook_planner_helpers
from cli.agent_cli.orchestration.taskbook_models import (
    TaskbookSnapshot,
    TaskCard,
    TaskCardState,
    new_orchestration_id,
)
from cli.agent_cli.orchestration.taskbook_planning_skill_models import (
    DEFAULT_SCOPE_PLACEHOLDER,
)
from cli.agent_cli.orchestration.taskbook_planning_skill_models import (
    TaskCardDraftSpec as _CardDraft,
)
from cli.agent_cli.orchestration.taskbook_planning_skills import (
    plan_plain_text_with_builtin_skills,
)
from cli.agent_cli.orchestration.taskbook_state import (
    TaskCardDependencyStatus,
    TaskCardExecutionMode,
    TaskCardExecutorRole,
    TaskCardKind,
    TaskCardStatus,
)


@dataclass(slots=True)
class TaskbookPlan:
    snapshot: TaskbookSnapshot
    cards: list[TaskCard]
    states: list[TaskCardState]
    source: str


def plan_taskbook_from_text(
    *,
    run_id: str,
    source_text: str,
    taskbook_id: str | None = None,
    version: int = 1,
    derived_from_version: int = 0,
    relaxed_markdown: bool = False,
) -> TaskbookPlan:
    raw = str(source_text or "").strip()
    if not raw:
        raise ValueError("source_text is required")

    if _looks_like_markdown(raw):
        objective, parsed_cards = _parse_markdown(raw, relaxed=relaxed_markdown)
        source = "markdown"
    else:
        objective, parsed_cards = _parse_plain_text(raw)
        source = "task_text"

    cards = _build_cards(parsed_cards, taskbook_version=version)
    _validate_cards(cards)

    states = [
        _initial_state(card.card_id, has_dependencies=bool(card.depends_on)) for card in cards
    ]
    snapshot = TaskbookSnapshot(
        taskbook_id=str(taskbook_id or new_orchestration_id("tb")),
        run_id=run_id,
        version=max(1, int(version)),
        derived_from_version=max(0, int(derived_from_version)),
        goal=objective,
        success_definition=["all cards accepted", "task objective fulfilled"],
        cards=[card.card_id for card in cards],
        critical_path=[card.card_id for card in cards],
        planner_summary=f"generated_from_{source}",
    )
    return TaskbookPlan(snapshot=snapshot, cards=cards, states=states, source=source)


def _parse_markdown(text: str, *, relaxed: bool = False) -> tuple[str, list[_CardDraft]]:
    lines = [line.rstrip() for line in text.splitlines()]
    objective = _extract_header_goal(lines)
    blocks = _split_card_blocks(lines)
    drafts: list[_CardDraft] = []
    for idx, block in enumerate(blocks, start=1):
        drafts.append(_card_from_block(block, index=idx, fallback_goal=objective, relaxed=relaxed))
    if not drafts:
        raise ValueError("no task cards found in markdown input")
    return objective, drafts


def _parse_plain_text(text: str) -> tuple[str, list[_CardDraft]]:
    objective = text.splitlines()[0].strip() if text.splitlines() else text.strip()
    skill_drafts = plan_plain_text_with_builtin_skills(text, objective=objective)
    if skill_drafts:
        return objective or "Task objective", skill_drafts
    kind = _infer_kind(text)
    execution_mode = _infer_execution_mode(text)
    owned_files = _extract_inline_list(text, "owned_files") or _extract_path_candidates(text)
    if not owned_files:
        owned_files = [DEFAULT_SCOPE_PLACEHOLDER]
    acceptance = _extract_inline_list(text, "acceptance_criteria")
    if not acceptance:
        acceptance = _default_acceptance_criteria(
            objective or text.strip() or "Task objective",
            kind=kind,
            owned_files=owned_files,
        )
    if _uses_placeholder_scope(owned_files) and kind == TaskCardKind.WORKSPACE_MUTATING:
        execution_mode = "stay_local"
    depends_on = _extract_inline_list(text, "depends_on")
    draft = _CardDraft(
        card_id="CARD-001",
        title=objective[:80] or "Task",
        goal=text.strip(),
        owned_files=owned_files,
        acceptance_criteria=acceptance,
        depends_on=depends_on,
        kind=kind,
        execution_mode=execution_mode,
        executor_role="executor",
    )
    return objective or "Task objective", [draft]


def _extract_header_goal(lines: Sequence[str]) -> str:
    return taskbook_planner_helpers.extract_header_goal(lines)


def _split_card_blocks(lines: Sequence[str]) -> list[list[str]]:
    return taskbook_planner_helpers.split_card_blocks(lines)


def _card_from_block(
    block: Sequence[str],
    *,
    index: int,
    fallback_goal: str,
    relaxed: bool = False,
) -> _CardDraft:
    heading = str(block[0] if block else f"### CARD-{index:03d}")
    title = heading.replace("###", "", 1).strip()
    parsed_id, parsed_title = _extract_card_id_and_title(title, index=index)
    fields = _parse_field_lines(block[1:])
    goal = fields.get("goal", [parsed_title or fallback_goal])[0]
    text_blob = "\n".join(block)
    kind = _infer_kind(text_blob, default=TaskCardKind.WORKSPACE_MUTATING)
    execution_mode = _explicit_execution_mode(fields) or _infer_execution_mode(text_blob)
    owned_files = list(fields.get("owned_files", []))
    if relaxed and not owned_files:
        owned_files = [DEFAULT_SCOPE_PLACEHOLDER]
    acceptance_criteria = list(fields.get("acceptance_criteria", []))
    if relaxed and not acceptance_criteria:
        acceptance_criteria = _default_acceptance_criteria(
            goal.strip() or fallback_goal,
            kind=kind,
            owned_files=owned_files,
        )
    if _uses_placeholder_scope(owned_files) and kind == TaskCardKind.WORKSPACE_MUTATING:
        execution_mode = "stay_local"
    return _CardDraft(
        card_id=parsed_id,
        title=parsed_title or parsed_id,
        goal=goal.strip() or fallback_goal,
        owned_files=owned_files,
        acceptance_criteria=acceptance_criteria,
        depends_on=fields.get("depends_on", []),
        kind=kind,
        execution_mode=execution_mode,
        executor_role=_infer_executor_role(text_blob),
    )


def _extract_card_id_and_title(text: str, *, index: int) -> tuple[str, str]:
    return taskbook_planner_helpers.extract_card_id_and_title(text, index=index)


def _parse_field_lines(lines: Sequence[str]) -> dict[str, list[str]]:
    return taskbook_planner_helpers.parse_field_lines(lines, split_list_fn=_split_list)


def _build_cards(drafts: Sequence[_CardDraft], *, taskbook_version: int) -> list[TaskCard]:
    cards: list[TaskCard] = []
    for draft in drafts:
        card = TaskCard(
            card_id=draft.card_id,
            taskbook_version=max(1, int(taskbook_version)),
            title=draft.title,
            goal=draft.goal,
            kind=draft.kind,
            owned_files=list(draft.owned_files),
            depends_on=list(draft.depends_on),
            can_run_in_parallel=draft.kind == TaskCardKind.READ_ONLY,
            execution_mode=TaskCardExecutionMode(str(draft.execution_mode)),
            executor_role=TaskCardExecutorRole(str(draft.executor_role)),
            acceptance_criteria=list(draft.acceptance_criteria),
        )
        cards.append(card)
    return cards


def _initial_state(card_id: str, *, has_dependencies: bool) -> TaskCardState:
    return TaskCardState(
        card_id=card_id,
        status=TaskCardStatus.DRAFT,
        dependency_status=(
            TaskCardDependencyStatus.PENDING
            if has_dependencies
            else TaskCardDependencyStatus.SATISFIED
        ),
        last_scheduler_decision="initial_planner_state",
    )


def _validate_cards(cards: Sequence[TaskCard]) -> None:
    seen: set[str] = set()
    for card in cards:
        if card.card_id in seen:
            raise ValueError(f"duplicate card_id: {card.card_id}")
        seen.add(card.card_id)
        if not card.owned_files:
            raise ValueError(f"card {card.card_id} missing owned scope")
        if not card.acceptance_criteria:
            raise ValueError(f"card {card.card_id} missing acceptance criteria")


def _looks_like_markdown(text: str) -> bool:
    return taskbook_planner_helpers.looks_like_markdown(text)


def _extract_inline_list(text: str, key: str) -> list[str]:
    return taskbook_planner_helpers.extract_inline_list(text, key, split_list_fn=_split_list)


def _split_list(value: str) -> list[str]:
    return taskbook_planner_helpers.split_list(value)


def _extract_path_candidates(text: str) -> list[str]:
    return taskbook_planner_helpers.extract_path_candidates(text)


def _default_acceptance_criteria(
    objective: str,
    *,
    kind: TaskCardKind,
    owned_files: Sequence[str],
) -> list[str]:
    objective_text = str(objective or "requested task").strip()
    criteria = [f"Advance the requested objective: {objective_text}"]
    if _uses_placeholder_scope(owned_files):
        criteria.append(
            "Refine owned_files into concrete repo paths before applying final code changes."
        )
    elif kind == TaskCardKind.READ_ONLY:
        criteria.append(
            "Capture concrete findings, decisions, or next-step recommendations for the operator."
        )
    else:
        criteria.append("Report the concrete files touched and the completed change scope.")
    return criteria


def _uses_placeholder_scope(owned_files: Sequence[str]) -> bool:
    return any(str(item).strip() == DEFAULT_SCOPE_PLACEHOLDER for item in owned_files)


def _infer_kind(text: str, *, default: TaskCardKind = TaskCardKind.READ_ONLY) -> TaskCardKind:
    normalized = str(text or "").lower()
    read_only_patterns = (
        "read-only",
        "read only",
        "research",
        "inspect",
        "scan",
        "summarize",
        "summary",
        "analyze",
        "investigate",
        "extract",
        "read",
        "调研",
        "检索",
        "提取",
        "查看",
        "阅读",
        "总结",
        "汇总",
    )
    if _contains_any(
        normalized,
        (
            "modify",
            "update",
            "patch",
            "refactor",
            "split",
            "break up",
            "改",
            "更新",
            "重构",
            "迁移",
            "拆分",
            "拆解",
        ),
    ):
        return TaskCardKind.WORKSPACE_MUTATING
    if _contains_any(normalized, ("continue current context", "context", "上下文")):
        return TaskCardKind.CONTEXT_SENSITIVE
    if _contains_any(normalized, ("benchmark", "长耗时", "long-running")):
        return TaskCardKind.CONTEXT_SENSITIVE
    if _contains_any(normalized, read_only_patterns):
        return TaskCardKind.READ_ONLY
    return default


def _infer_execution_mode(text: str) -> str:
    normalized = str(text or "").lower()
    if _contains_any(
        normalized, ("visible_child_tab", "visible child tab", "visible child", "child tab")
    ):
        return "visible_child_tab"
    if _contains_any(normalized, ("background teammate", "background", "后台", "worker")):
        return "background_teammate"
    if _contains_any(normalized, ("subagent", "delegated subagent")):
        return "delegated_subagent"
    if _contains_any(normalized, ("teammate", "delegated teammate")):
        return "delegated_teammate"
    if _contains_any(normalized, ("background task", "benchmark", "smoke")):
        return "background_task"
    return "stay_local"


def _explicit_execution_mode(fields: dict[str, list[str]]) -> str:
    raw = " ".join(str(item or "") for item in list(fields.get("execution_mode") or [])).strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "visible_child": "visible_child_tab",
        "visible_child_tab": "visible_child_tab",
        "child_tab": "visible_child_tab",
        "background": "background_teammate",
        "background_teammate": "background_teammate",
        "background_task": "background_task",
        "delegated_subagent": "delegated_subagent",
        "subagent": "delegated_subagent",
        "delegated_teammate": "delegated_teammate",
        "teammate": "delegated_teammate",
        "stay_local": "stay_local",
        "local": "stay_local",
    }
    return aliases.get(normalized, "")


def _infer_executor_role(text: str) -> str:
    normalized = str(text or "").lower()
    if _contains_any(normalized, ("review", "reviewer", "审核")):
        return "reviewer"
    if _contains_any(normalized, ("research", "scout", "调研")):
        return "scout"
    return "executor"


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return taskbook_planner_helpers.contains_any(
        text, patterns, contains_pattern_fn=_contains_pattern
    )


def _contains_pattern(text: str, token: str) -> bool:
    return taskbook_planner_helpers.contains_pattern(
        text,
        token,
        ascii_token_boundary_safe_fn=_ascii_token_boundary_safe,
    )


def _ascii_token_boundary_safe(token: str) -> bool:
    return taskbook_planner_helpers.ascii_token_boundary_safe(token)
