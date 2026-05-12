from __future__ import annotations

from typing import Any


def _orchestration_preview_request_text(payload: dict[str, Any]) -> str:
    preview = dict(payload.get("preview") or {})
    lines = ["orchestration preview ready"]
    lines.append(f"status={payload.get('status') or 'preview_ready'}")
    lines.append(
        f"confirmation_required={str(bool(payload.get('confirmation_required', True))).lower()}"
    )
    lines.append(f"next_action={payload.get('next_action') or 'show_preview_confirm_ui'}")
    lines.append(f"preview_id={preview.get('preview_id') or '-'}")
    lines.append(f"objective={preview.get('objective') or '-'}")
    lines.append(f"routing_mode={preview.get('routing_mode') or '-'}")
    lines.append(f"taskbook_version={int(preview.get('taskbook_version') or 0)}")
    lines.append(f"card_count={int(preview.get('card_count') or 0)}")
    lines.append(
        "ready_card_ids="
        + ",".join(str(item) for item in list(preview.get("ready_card_ids") or []))
        if preview.get("ready_card_ids")
        else "ready_card_ids=-"
    )
    lines.append(
        "blocked_card_ids="
        + ",".join(str(item) for item in list(preview.get("blocked_card_ids") or []))
        if preview.get("blocked_card_ids")
        else "blocked_card_ids=-"
    )
    adjustment_lines = [
        str(item).strip()
        for item in list(preview.get("planning_adjustment_lines") or [])
        if str(item).strip()
    ]
    lines.append(
        "planning_adjustment_lines=" + " | ".join(adjustment_lines)
        if adjustment_lines
        else "planning_adjustment_lines=-"
    )
    return "\n".join(lines)


def _orchestration_preview_summary(preview: dict[str, Any]) -> str:
    lines = ["Taskbook preview"]
    lines.append(f"Goal: {preview.get('objective') or '-'}")
    lines.append(f"Routing: {preview.get('routing_mode') or '-'}")
    routing_reasons = [
        str(item).strip()
        for item in list(preview.get("routing_reasons") or [])
        if str(item).strip()
    ]
    if routing_reasons:
        lines.append("Routing reasons: " + ", ".join(routing_reasons))
    planner = " / ".join(
        part
        for part in (
            str(preview.get("planner_provider") or "").strip(),
            str(preview.get("planner_model") or "").strip(),
            str(preview.get("planner_reasoning_effort") or "").strip(),
        )
        if part
    )
    if planner:
        lines.append(f"Planner: {planner}")
    lines.append(
        "Cards: "
        f"{int(preview.get('card_count') or 0)} "
        f"(ready {len(list(preview.get('ready_card_ids') or []))}, "
        f"blocked {len(list(preview.get('blocked_card_ids') or []))})"
    )
    adjustment_lines = [
        str(item).strip()
        for item in list(preview.get("planning_adjustment_lines") or [])
        if str(item).strip()
    ]
    if adjustment_lines:
        lines.append("Current planning adjustments:")
        lines.extend(f"- {item}" for item in adjustment_lines)
    cards = [dict(item) for item in list(preview.get("cards") or []) if isinstance(item, dict)]
    state_index = {
        str(item.get("card_id") or "").strip(): dict(item)
        for item in list(preview.get("card_states") or [])
        if isinstance(item, dict)
    }
    if cards:
        lines.append("Cards preview:")
    for card in cards[:3]:
        card_id = str(card.get("card_id") or "").strip() or "-"
        title = str(card.get("title") or "").strip() or "-"
        files = [
            str(item).strip() for item in list(card.get("owned_files") or []) if str(item).strip()
        ]
        file_summary = ", ".join(files[:2]) if files else "-"
        state = state_index.get(card_id, {})
        status = str(state.get("status") or "").strip() or "-"
        mode = str(card.get("execution_mode") or "").strip() or "-"
        lines.append(
            f"- {card_id} | {title} | status={status} | mode={mode} | files={file_summary}"
        )
    remaining = len(cards) - 3
    if remaining > 0:
        lines.append(f"- ... {remaining} more cards")
    lines.append("")
    lines.append("Choose the next action.")
    return "\n".join(lines)


def _orchestration_preview_full(preview: dict[str, Any]) -> str:
    lines = ["Taskbook preview (full)"]
    lines.append(f"Goal: {preview.get('objective') or '-'}")
    lines.append(f"Routing: {preview.get('routing_mode') or '-'}")
    routing_reasons = [
        str(item).strip()
        for item in list(preview.get("routing_reasons") or [])
        if str(item).strip()
    ]
    if routing_reasons:
        lines.append("Routing reasons: " + ", ".join(routing_reasons))
    adjustment_lines = [
        str(item).strip()
        for item in list(preview.get("planning_adjustment_lines") or [])
        if str(item).strip()
    ]
    if adjustment_lines:
        lines.append("Planning adjustments:")
        lines.extend(f"- {item}" for item in adjustment_lines)
    success_definition = [
        str(item).strip()
        for item in list(dict(preview.get("taskbook") or {}).get("success_definition") or [])
        if str(item).strip()
    ]
    if success_definition:
        lines.append("Success definition:")
        lines.extend(f"- {item}" for item in success_definition)
    cards = [dict(item) for item in list(preview.get("cards") or []) if isinstance(item, dict)]
    state_index = {
        str(item.get("card_id") or "").strip(): dict(item)
        for item in list(preview.get("card_states") or [])
        if isinstance(item, dict)
    }
    for card in cards:
        card_id = str(card.get("card_id") or "").strip() or "-"
        title = str(card.get("title") or "").strip() or "-"
        lines.append("")
        lines.append(f"### {card_id}: {title}")
        lines.append(f"- goal: {card.get('goal') or '-'}")
        state = state_index.get(card_id, {})
        lines.append(f"- status_if_started_now: {state.get('status') or '-'}")
        lines.append(f"- execution_mode: {card.get('execution_mode') or '-'}")
        lines.append(
            f"- can_run_in_parallel: {'true' if bool(card.get('can_run_in_parallel')) else 'false'}"
        )
        owned_files = [
            str(item).strip() for item in list(card.get("owned_files") or []) if str(item).strip()
        ]
        lines.append("- owned_files: " + (", ".join(owned_files) if owned_files else "-"))
        depends_on = [
            str(item).strip() for item in list(card.get("depends_on") or []) if str(item).strip()
        ]
        lines.append("- depends_on: " + (", ".join(depends_on) if depends_on else "-"))
        acceptance = [
            str(item).strip()
            for item in list(card.get("acceptance_criteria") or [])
            if str(item).strip()
        ]
        lines.append("- acceptance_criteria: " + (" | ".join(acceptance) if acceptance else "-"))
        risk_hints = [
            str(item).strip() for item in list(card.get("risk_hints") or []) if str(item).strip()
        ]
        if risk_hints:
            lines.append("- risk_hints: " + " | ".join(risk_hints))
        handoff = [
            str(item).strip()
            for item in list(card.get("handoff_requirements") or [])
            if str(item).strip()
        ]
        if handoff:
            lines.append("- handoff_requirements: " + " | ".join(handoff))
    lines.append("")
    lines.append("Choose the next action.")
    return "\n".join(lines)
