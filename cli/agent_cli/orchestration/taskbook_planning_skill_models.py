from __future__ import annotations

from dataclasses import dataclass

from cli.agent_cli.orchestration.taskbook_state import TaskCardKind

DEFAULT_SCOPE_PLACEHOLDER = "<scope-to-confirm>"


@dataclass(slots=True)
class TaskCardDraftSpec:
    card_id: str
    title: str
    goal: str
    owned_files: list[str]
    acceptance_criteria: list[str]
    depends_on: list[str]
    kind: TaskCardKind
    execution_mode: str
    executor_role: str
