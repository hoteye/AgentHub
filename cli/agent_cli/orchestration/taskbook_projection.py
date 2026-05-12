from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    TaskCard,
    TaskCardState,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


def render_taskbook_projection(bundle: Any) -> str:
    run = _bundle_get(bundle, "run")
    taskbook = _bundle_get(bundle, "latest_taskbook")
    card_specs = dict(_bundle_get(bundle, "card_specs", default={}))
    card_states = dict(_bundle_get(bundle, "card_states", default={}))
    card_results = dict(_bundle_get(bundle, "card_results", default={}))
    card_acceptance = dict(_bundle_get(bundle, "card_acceptance", default={}))
    latest_result = _latest_result_across_cards(card_results)
    latest_acceptance = _latest_acceptance_across_cards(card_acceptance)
    run_ready = len(list(run.ready_card_ids or []))
    run_running = len(list(run.running_card_ids or []))
    run_blocked = len(list(run.blocked_card_ids or []))
    run_completed = len(list(run.completed_card_ids or []))
    lines = [
        f"# {taskbook.goal if taskbook is not None and taskbook.goal else run.objective or run.run_id}",
        "",
        f"- run_id: {run.run_id}",
        f"- status: {run.status.value}",
        f"- current_phase: {run.current_phase or '-'}",
        f"- taskbook_version: {run.taskbook_version_current}",
        f"- cards_total: {len(card_specs)}",
        f"- cards_ready: {run_ready}",
        f"- cards_running: {run_running}",
        f"- cards_blocked: {run_blocked}",
        f"- cards_completed: {run_completed}",
    ]
    lines.append(f"- accepted_facts: {'; '.join(run.accepted_facts) if run.accepted_facts else '-'}")
    if latest_result is not None:
        lines.append(
            "- latest_result: "
            f"{latest_result.card_id}:{latest_result.result_id} | {latest_result.status.value} | {latest_result.summary or '-'}"
        )
    else:
        lines.append("- latest_result: -")
    if latest_acceptance is not None:
        lines.append(
            "- latest_acceptance: "
            f"{latest_acceptance.card_id}:{latest_acceptance.acceptance_id} | "
            f"{latest_acceptance.decision.value} | {latest_acceptance.reason or '-'}"
        )
    else:
        lines.append("- latest_acceptance: -")
    lines.append("")
    lines.append("## Cards")
    for card_id in sorted(card_specs):
        card = card_specs[card_id]
        state = card_states.get(card_id)
        results = list(card_results.get(card_id) or [])
        acceptances = list(card_acceptance.get(card_id) or [])
        latest_card_result = results[-1] if results else None
        latest_card_acceptance = acceptances[-1] if acceptances else None
        lines.extend(
            [
                f"### {card.card_id}: {card.title or card.goal or card.card_id}",
                f"- kind: {card.kind.value}",
                f"- status: {state.status.value if state is not None else 'unknown'}",
                f"- attempt: {state.attempt if state is not None else 0}",
                f"- last_scheduler_decision: {state.last_scheduler_decision if state is not None and state.last_scheduler_decision else '-'}",
                f"- goal: {card.goal or '-'}",
                f"- owned_files: {', '.join(card.owned_files) if card.owned_files else '-'}",
                f"- acceptance_criteria: {'; '.join(card.acceptance_criteria) if card.acceptance_criteria else '-'}",
                f"- latest_result: {_result_summary_text(latest_card_result)}",
                f"- latest_acceptance: {_acceptance_summary_text(latest_card_acceptance)}",
                f"- blockers: {_result_blocker_text(latest_card_result)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_card_projection(
    card: TaskCard,
    *,
    state: TaskCardState | None = None,
    latest_result: CardResult | None = None,
    latest_acceptance: CardAcceptance | None = None,
) -> str:
    lines = [
        f"# {card.card_id}: {card.title or card.goal or card.card_id}",
        "",
        f"- kind: {card.kind.value}",
        f"- status: {state.status.value if state is not None else 'unknown'}",
        f"- attempt: {state.attempt if state is not None else 0}",
        f"- dependency_status: {state.dependency_status.value if state is not None else '-'}",
        f"- last_scheduler_decision: {state.last_scheduler_decision if state is not None and state.last_scheduler_decision else '-'}",
        f"- goal: {card.goal or '-'}",
        f"- owned_files: {', '.join(card.owned_files) if card.owned_files else '-'}",
        f"- depends_on: {', '.join(card.depends_on) if card.depends_on else '-'}",
        f"- acceptance_criteria: {'; '.join(card.acceptance_criteria) if card.acceptance_criteria else '-'}",
    ]
    if latest_result is not None:
        lines.append(f"- latest_result: {latest_result.result_id} | {latest_result.status.value} | {latest_result.summary or '-'}")
        lines.append(f"- latest_result_modified_files: {', '.join(latest_result.modified_files) if latest_result.modified_files else '-'}")
        lines.append(f"- latest_result_test_commands: {', '.join(latest_result.test_commands) if latest_result.test_commands else '-'}")
        lines.append(f"- latest_result_blockers: {'; '.join(latest_result.blockers) if latest_result.blockers else '-'}")
    else:
        lines.append("- latest_result: -")
    if latest_acceptance is not None:
        lines.append(
            f"- latest_acceptance: {latest_acceptance.acceptance_id} | {latest_acceptance.decision.value} | {latest_acceptance.reason or '-'}"
        )
        lines.append(
            "- latest_acceptance_reviewer: "
            f"{latest_acceptance.reviewer_provider or '-'} | {latest_acceptance.reviewer_model or '-'}"
        )
    else:
        lines.append("- latest_acceptance: -")
    return "\n".join(lines).rstrip() + "\n"


def build_workflows_view(bundle: Any) -> Dict[str, Any]:
    run = _bundle_get(bundle, "run")
    card_specs = dict(_bundle_get(bundle, "card_specs", default={}))
    card_states = dict(_bundle_get(bundle, "card_states", default={}))
    card_results = dict(_bundle_get(bundle, "card_results", default={}))
    card_acceptance = dict(_bundle_get(bundle, "card_acceptance", default={}))
    cards: list[Dict[str, Any]] = []
    for card_id in sorted(card_specs):
        card = card_specs[card_id]
        state = card_states.get(card_id)
        results = card_results.get(card_id, [])
        acceptances = card_acceptance.get(card_id, [])
        latest_result = results[-1] if results else None
        latest_acceptance = acceptances[-1] if acceptances else None
        cards.append(
            {
                "card_id": card.card_id,
                "title": card.title,
                "kind": card.kind.value,
                "status": state.status.value if state is not None else "unknown",
                "last_scheduler_decision": str(state.last_scheduler_decision or "") if state is not None else "",
                "latest_result": latest_result.to_dict() if latest_result is not None else None,
                "latest_acceptance": latest_acceptance.to_dict() if latest_acceptance is not None else None,
            }
        )
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "current_phase": run.current_phase,
        "taskbook_version_current": run.taskbook_version_current,
        "accepted_facts": list(run.accepted_facts),
        "cards": cards,
    }


def write_projections(storage: TaskbookStorage, run_id: str) -> Dict[str, Path]:
    bundle = storage.load_run_bundle(run_id)
    if bundle is None:
        raise ValueError(f"unknown run_id: {run_id}")
    run_dir = storage.run_dir(run_id)
    taskbook_path = run_dir / "projections" / "taskbook.md"
    taskbook_path.parent.mkdir(parents=True, exist_ok=True)
    taskbook_path.write_text(render_taskbook_projection(bundle), encoding="utf-8")

    card_specs = dict(_bundle_get(bundle, "card_specs", default={}))
    card_states = dict(_bundle_get(bundle, "card_states", default={}))
    card_results = dict(_bundle_get(bundle, "card_results", default={}))
    card_acceptance = dict(_bundle_get(bundle, "card_acceptance", default={}))
    card_paths: Dict[str, Path] = {}
    for card_id, card in sorted(card_specs.items()):
        card_path = run_dir / "projections" / "cards" / f"{card_id}.md"
        card_path.parent.mkdir(parents=True, exist_ok=True)
        results = card_results.get(card_id, [])
        acceptances = card_acceptance.get(card_id, [])
        card_path.write_text(
            render_card_projection(
                card,
                state=card_states.get(card_id),
                latest_result=results[-1] if results else None,
                latest_acceptance=acceptances[-1] if acceptances else None,
            ),
            encoding="utf-8",
        )
        card_paths[card_id] = card_path
    return {"taskbook": taskbook_path, **{f"card:{card_id}": path for card_id, path in card_paths.items()}}


def _bundle_get(bundle: Any, key: str, *, default: Any = None) -> Any:
    if isinstance(bundle, dict):
        if key in bundle:
            return bundle[key]
        if key == "latest_taskbook":
            taskbooks = list(bundle.get("taskbooks") or [])
            return taskbooks[-1] if taskbooks else default
        return default
    return getattr(bundle, key, default)


def _latest_result_across_cards(card_results: dict[str, Any]) -> CardResult | None:
    latest: CardResult | None = None
    latest_key: tuple[str, str] = ("", "")
    for items in card_results.values():
        for item in list(items or []):
            if not isinstance(item, CardResult):
                continue
            key = (str(item.reported_at or ""), str(item.result_id or ""))
            if latest is None or key > latest_key:
                latest = item
                latest_key = key
    return latest


def _latest_acceptance_across_cards(card_acceptance: dict[str, Any]) -> CardAcceptance | None:
    latest: CardAcceptance | None = None
    latest_key: tuple[str, str] = ("", "")
    for items in card_acceptance.values():
        for item in list(items or []):
            if not isinstance(item, CardAcceptance):
                continue
            key = (str(item.reviewed_at or ""), str(item.acceptance_id or ""))
            if latest is None or key > latest_key:
                latest = item
                latest_key = key
    return latest


def _result_summary_text(result: CardResult | None) -> str:
    if result is None:
        return "-"
    return f"{result.result_id} | {result.status.value} | {result.summary or '-'}"


def _acceptance_summary_text(acceptance: CardAcceptance | None) -> str:
    if acceptance is None:
        return "-"
    return f"{acceptance.acceptance_id} | {acceptance.decision.value} | {acceptance.reason or '-'}"


def _result_blocker_text(result: CardResult | None) -> str:
    if result is None:
        return "-"
    return "; ".join(result.blockers) if result.blockers else "-"
