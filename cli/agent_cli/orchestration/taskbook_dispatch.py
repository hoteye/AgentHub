from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.background_tasks.adapter import enqueue_background_task
from cli.agent_cli.background_tasks.models import BackgroundTaskType
from cli.agent_cli.orchestration.taskbook_models import (
    ComplexTaskRun,
    ExecutionRef,
    TaskCard,
    TaskCardState,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_state import (
    ExecutionRefKind,
    TaskCardExecutionMode,
    TaskCardKind,
    TaskCardStatus,
)

_STRUCTURED_GOAL_PREFIXES = (
    "owned_files:",
    "owned files:",
    "owned file:",
    "acceptance_criteria:",
    "acceptance criteria:",
    "test_requirements:",
    "test requirements:",
    "risk_hints:",
    "risk hints:",
    "allowed_paths:",
    "allowed paths:",
    "blocked_paths:",
    "blocked paths:",
)


@dataclass(slots=True)
class TaskCardDispatchResult:
    card: TaskCard
    state: TaskCardState
    execution_ref: ExecutionRef
    backend: str
    raw_handle: Any = None


def _clean_goal_text(card: TaskCard) -> str:
    raw_goal = str(card.goal or "").strip()
    if not raw_goal:
        return ""
    normalized_title = " ".join(str(card.title or "").strip().lower().replace("_", " ").split())
    cleaned_lines: list[str] = []
    seen_lines: set[str] = set()
    for raw_line in raw_goal.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        normalized_line = " ".join(line.lower().replace("_", " ").split())
        if normalized_line == normalized_title:
            continue
        if any(normalized_line.startswith(prefix) for prefix in _STRUCTURED_GOAL_PREFIXES):
            continue
        if normalized_line in seen_lines:
            continue
        seen_lines.add(normalized_line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def build_teammate_task_text(card: TaskCard) -> str:
    title = str(card.title or card.card_id).strip() or card.card_id
    effective_allowed_paths = list(card.allowed_paths or card.owned_files)
    lines = [title]
    goal_text = _clean_goal_text(card)
    if goal_text:
        lines.append(f"Goal: {goal_text}")
    lines.extend(
        [
            "Execution contract:",
            "- Treat the current working directory as the isolated workspace root for this task.",
            "- Use relative workspace paths and stay inside the workspace root; do not target live absolute repo paths.",
            "- Make the smallest change that satisfies the acceptance criteria.",
        ]
    )
    if card.owned_files:
        lines.append(
            "- Start with the owned files directly and only widen search if those files clearly reference another dependency you need."
        )
        lines.append("Owned files: " + ", ".join(card.owned_files))
    if effective_allowed_paths:
        lines.append(
            "- Keep reads and edits within the allowed paths; avoid broad whole-repo scans."
        )
        lines.append("Allowed paths: " + ", ".join(effective_allowed_paths))
    if card.blocked_paths:
        lines.append("Blocked paths: " + ", ".join(card.blocked_paths))
    if card.acceptance_criteria:
        lines.append("Acceptance criteria: " + "; ".join(card.acceptance_criteria))
    if card.test_requirements:
        lines.append("Test requirements: " + "; ".join(card.test_requirements))
    if card.risk_hints:
        lines.append("Risk hints: " + "; ".join(card.risk_hints))
    return "\n".join(lines).strip()


def dispatch_task_card(
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    *,
    runtime: Any | None = None,
    background_adapter: Any | None = None,
    enqueue_background_task_fn: Callable[..., Any] = enqueue_background_task,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: int | None = None,
    cwd: str | None = None,
) -> TaskCardDispatchResult:
    updated_state = TaskCardState.from_dict(state.to_dict())
    dispatch_at = utc_now_iso()
    if not updated_state.queued_at:
        updated_state.queued_at = dispatch_at
    updated_state.started_at = dispatch_at
    updated_state.updated_at = dispatch_at
    updated_state.status = TaskCardStatus.RUNNING

    if card.execution_mode is TaskCardExecutionMode.VISIBLE_CHILD_TAB:
        backend = (
            getattr(runtime, "visible_child_tab_backend", None) if runtime is not None else None
        )
        dispatcher = getattr(backend, "dispatch_visible_child_task", None)
        if not callable(dispatcher):
            raise RuntimeError("visible child tab backend is not available")
        parent_tab_id = str(getattr(runtime, "visible_child_parent_tab_id", "") or "").strip()
        if not parent_tab_id:
            parent_tab_id = str(getattr(backend, "active_tab_id", "") or "")
        payload = dict(
            dispatcher(
                parent_tab_id=parent_tab_id,
                task_text=build_teammate_task_text(card),
                metadata={
                    "run_id": run.run_id,
                    "card_id": card.card_id,
                    "attempt": int(updated_state.attempt or 0),
                },
            )
        )
        execution_ref = ExecutionRef(
            kind=ExecutionRefKind.VISIBLE_CHILD_TAB,
            task_id=str(payload.get("task_id") or ""),
            agent_id=str(payload.get("tab_id") or payload.get("agent_id") or ""),
            provider_name=str(payload.get("provider_name") or provider or ""),
            model=str(payload.get("model") or model or ""),
            route_label=str(payload.get("route_label") or "dispatch_visible_child_tab"),
        )
        updated_state.execution_refs.append(execution_ref)
        updated_state.last_scheduler_decision = "dispatched_via_visible_child_tab"
        return TaskCardDispatchResult(
            card=card,
            state=updated_state,
            execution_ref=execution_ref,
            backend="visible_child_tab",
            raw_handle=payload,
        )

    if card.kind is TaskCardKind.READ_ONLY:
        if runtime is None:
            raise RuntimeError("runtime is required to dispatch read_only cards")
        result = runtime.spawn_agent_result(
            task=build_teammate_task_text(card),
            role="subagent",
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            async_mode=True,
            mode="background",
            reason="task_card_dispatch",
            wait_required=False,
            task_shape="read_only",
        )
        payload = _tool_payload(result)
        execution_ref = ExecutionRef(
            kind=ExecutionRefKind.DELEGATED_SUBAGENT,
            agent_id=str(payload.get("agent_id") or ""),
            provider_name=str(payload.get("provider_name") or provider or ""),
            model=str(payload.get("model") or model or ""),
            route_label="dispatch_read_only",
        )
        updated_state.execution_refs.append(execution_ref)
        updated_state.last_scheduler_decision = "dispatched_via_delegated_subagent"
        return TaskCardDispatchResult(
            card=card,
            state=updated_state,
            execution_ref=execution_ref,
            backend="delegated_subagent",
            raw_handle=result,
        )

    task_type, payload = _background_request_for_card(
        run,
        card,
        cwd=cwd,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
    )
    handle = enqueue_background_task_fn(
        task_type=task_type,
        payload=payload,
        source="taskbook_dispatch",
        thread_id=run.thread_id,
        adapter=background_adapter,
        force_enable=background_adapter is None,
    )
    execution_ref = ExecutionRef(
        kind=ExecutionRefKind.BACKGROUND_TASK,
        task_id=str(getattr(handle, "task_id", "") or ""),
        provider_name=str(provider or ""),
        model=str(model or ""),
        route_label=f"dispatch_{task_type.value}",
    )
    updated_state.execution_refs.append(execution_ref)
    updated_state.last_scheduler_decision = f"dispatched_via_{task_type.value}"
    return TaskCardDispatchResult(
        card=card,
        state=updated_state,
        execution_ref=execution_ref,
        backend=task_type.value,
        raw_handle=handle,
    )


def _background_request_for_card(
    run: ComplexTaskRun,
    card: TaskCard,
    *,
    cwd: str | None,
    provider: str | None,
    model: str | None,
    reasoning_effort: str | None,
    timeout_seconds: int | None,
) -> tuple[BackgroundTaskType, dict[str, Any]]:
    normalized_text = f"{card.title}\n{card.goal}".lower()
    allowed_paths = list(card.allowed_paths or card.owned_files)
    if (
        card.execution_mode is TaskCardExecutionMode.BACKGROUND_TASK
        and "benchmark" in normalized_text
    ):
        return (
            BackgroundTaskType.BENCHMARK,
            {
                "case": card.goal or card.title or card.card_id,
                **({"cwd": str(cwd)} if str(cwd or "").strip() else {}),
            },
        )
    if card.execution_mode is TaskCardExecutionMode.BACKGROUND_TASK:
        return (
            BackgroundTaskType.SMOKE,
            {
                "kind": card.goal or card.title or card.card_id,
                **({"cwd": str(cwd)} if str(cwd or "").strip() else {}),
            },
        )
    return (
        BackgroundTaskType.TEAMMATE,
        {
            "task": build_teammate_task_text(card),
            **({"cwd": str(cwd)} if str(cwd or "").strip() else {}),
            **({"provider": str(provider)} if str(provider or "").strip() else {}),
            **({"model": str(model)} if str(model or "").strip() else {}),
            **(
                {"reasoning_effort": str(reasoning_effort)}
                if str(reasoning_effort or "").strip()
                else {}
            ),
            **({"timeout_seconds": int(timeout_seconds)} if timeout_seconds is not None else {}),
            "sandbox_mode": (
                "workspace-write" if card.kind is not TaskCardKind.READ_ONLY else "read-only"
            ),
            "run_id": run.run_id,
            "card_id": card.card_id,
            "allowed_paths": allowed_paths,
            "blocked_paths": list(card.blocked_paths),
            "owned_files": list(card.owned_files),
            "acceptance_criteria": list(card.acceptance_criteria),
            "test_requirements": list(card.test_requirements),
        },
    )


def _tool_payload(result: Any) -> dict[str, Any]:
    tool_events = list(getattr(result, "tool_events", []) or [])
    if not tool_events:
        return {}
    payload = getattr(tool_events[0], "payload", None)
    return dict(payload) if isinstance(payload, dict) else {}
