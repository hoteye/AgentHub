from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.orchestration_commands_helpers_runtime_text_child_tasks import (
    _child_tab_send_text,
    _child_tab_spawn_text,
    _child_task_wait_text,
)
from cli.agent_cli.runtime_core.orchestration_commands_helpers_runtime_text_preview import (
    _orchestration_preview_full,
    _orchestration_preview_request_text,
    _orchestration_preview_summary,
)

__all__ = [
    "_child_tab_send_text",
    "_child_tab_spawn_text",
    "_child_task_wait_text",
    "_orchestrate_confirmation_text",
    "_orchestrate_continue_text",
    "_orchestrate_created_text",
    "_orchestrate_dispatch_text",
    "_orchestrate_progress_text",
    "_orchestrate_review_text",
    "_orchestration_preview_full",
    "_orchestration_preview_request_text",
    "_orchestration_preview_summary",
    "_truncate_prompt_text",
]


def _orchestrate_created_text(payload: dict[str, Any]) -> str:
    lines = ["orchestration run created"]
    lines.append(f"run_id={payload.get('run_id') or '-'}")
    lines.append(f"mode={payload.get('mode') or '-'}")
    lines.append(f"routing_mode={payload.get('routing_mode') or '-'}")
    routing_reasons = list(payload.get("routing_reasons") or [])
    if routing_reasons:
        lines.append(
            "routing_reasons="
            + ",".join(str(item) for item in routing_reasons if str(item).strip())
        )
    lines.append(f"status={payload.get('status') or '-'}")
    lines.append(f"current_phase={payload.get('current_phase') or '-'}")
    lines.append(f"taskbook_source={payload.get('taskbook_source') or '-'}")
    lines.append(f"taskbook_version={payload.get('taskbook_version') or 0}")
    lines.append(f"cards={payload.get('card_count') or 0}")
    lines.append(f"ready_cards={len(list(payload.get('ready_card_ids') or []))}")
    lines.append(f"running_cards={len(list(payload.get('running_card_ids') or []))}")
    lines.append(f"blocked_cards={len(list(payload.get('blocked_card_ids') or []))}")
    lines.append(f"completed_cards={len(list(payload.get('completed_card_ids') or []))}")
    lines.append(f"run_path={payload.get('run_path') or '-'}")
    lines.append(f"projection_path={payload.get('projection_path') or '-'}")
    return "\n".join(lines)


def _orchestrate_confirmation_text(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip()
    preview = dict(payload.get("preview") or {})
    if status == "confirmed":
        lines = ["orchestration confirmation accepted"]
        adjustment_lines = list(payload.get("planning_adjustment_lines") or [])
        if adjustment_lines:
            lines.append(
                "planning_adjustments=" + " | ".join(str(item) for item in adjustment_lines)
            )
        created_text = _orchestrate_created_text(dict(payload.get("created_run") or {}))
        dispatch_text = _orchestrate_dispatch_text(dict(payload.get("dispatch_run") or {}))
        lines.append(created_text)
        if "run_id=-" not in dispatch_text:
            lines.append(dispatch_text)
        return "\n".join(lines)
    if status == "interactive_unavailable":
        lines = [
            "orchestration confirmation unavailable: interactive request_user_input handler missing",
            _orchestration_preview_summary(preview),
            "fallback: use /orchestrate directly, or retry inside the interactive TUI/app-server session",
        ]
        return "\n\n".join(item for item in lines if str(item).strip())
    lines = [
        "orchestration confirmation cancelled",
        "no orchestration run was created",
    ]
    if preview:
        lines.append(_orchestration_preview_summary(preview))
    return "\n\n".join(lines)


def _orchestrate_dispatch_text(payload: dict[str, Any]) -> str:
    dispatch_error = str(payload.get("dispatch_error") or "").strip()
    lines = [
        "orchestration dispatch failed" if dispatch_error else "orchestration dispatch submitted"
    ]
    lines.append(f"run_id={payload.get('run_id') or '-'}")
    lines.append(f"status={payload.get('status') or '-'}")
    lines.append(f"current_phase={payload.get('current_phase') or '-'}")
    if dispatch_error:
        lines.append(f"dispatch_error={dispatch_error}")
    lines.append(
        "selected_cards="
        + ",".join(str(item) for item in list(payload.get("selected_card_ids") or []))
        if payload.get("selected_card_ids")
        else "selected_cards=-"
    )
    lines.append(
        "dispatched_cards="
        + ",".join(str(item) for item in list(payload.get("dispatched_card_ids") or []))
        if payload.get("dispatched_card_ids")
        else "dispatched_cards=-"
    )
    lines.append(
        "dispatch_refs=" + ",".join(str(item) for item in list(payload.get("dispatch_refs") or []))
        if payload.get("dispatch_refs")
        else "dispatch_refs=-"
    )
    lines.append(f"ready_cards={len(list(payload.get('ready_card_ids') or []))}")
    lines.append(f"running_cards={len(list(payload.get('running_card_ids') or []))}")
    lines.append(f"blocked_cards={len(list(payload.get('blocked_card_ids') or []))}")
    lines.append(f"completed_cards={len(list(payload.get('completed_card_ids') or []))}")
    return "\n".join(lines)


def _orchestrate_progress_text(payload: dict[str, Any]) -> str:
    synced_cards = [
        str(item) for item in list(payload.get("synced_card_ids") or []) if str(item).strip()
    ]
    accepted_cards = [
        str(item) for item in list(payload.get("accepted_card_ids") or []) if str(item).strip()
    ]
    unlocked_cards = [
        str(item) for item in list(payload.get("unlocked_card_ids") or []) if str(item).strip()
    ]
    pending_review_cards = [
        card_id for card_id in synced_cards if card_id not in set(accepted_cards)
    ]
    lines = ["orchestration progress updated"]
    lines.append(f"run_id={payload.get('run_id') or '-'}")
    lines.append(f"status={payload.get('status') or '-'}")
    lines.append(f"current_phase={payload.get('current_phase') or '-'}")
    lines.append(
        "synced_cards=" + ",".join(str(item) for item in list(payload.get("synced_card_ids") or []))
        if payload.get("synced_card_ids")
        else "synced_cards=-"
    )
    lines.append(
        "accepted_cards="
        + ",".join(str(item) for item in list(payload.get("accepted_card_ids") or []))
        if payload.get("accepted_card_ids")
        else "accepted_cards=-"
    )
    lines.append(
        "unlocked_cards="
        + ",".join(str(item) for item in list(payload.get("unlocked_card_ids") or []))
        if payload.get("unlocked_card_ids")
        else "unlocked_cards=-"
    )
    lines.append(f"acceptance_applied_count={len(accepted_cards)}")
    lines.append(f"review_pending_count={len(pending_review_cards)}")
    lines.append(
        "review_pending_cards=" + ",".join(pending_review_cards)
        if pending_review_cards
        else "review_pending_cards=-"
    )
    lines.append(f"acceptance_unlocked_count={len(unlocked_cards)}")
    lines.append(
        "selected_cards="
        + ",".join(str(item) for item in list(payload.get("selected_card_ids") or []))
        if payload.get("selected_card_ids")
        else "selected_cards=-"
    )
    lines.append(
        "dispatched_cards="
        + ",".join(str(item) for item in list(payload.get("dispatched_card_ids") or []))
        if payload.get("dispatched_card_ids")
        else "dispatched_cards=-"
    )
    lines.append(
        "dispatch_refs=" + ",".join(str(item) for item in list(payload.get("dispatch_refs") or []))
        if payload.get("dispatch_refs")
        else "dispatch_refs=-"
    )
    lines.append(f"ready_cards={len(list(payload.get('ready_card_ids') or []))}")
    lines.append(f"running_cards={len(list(payload.get('running_card_ids') or []))}")
    lines.append(f"blocked_cards={len(list(payload.get('blocked_card_ids') or []))}")
    lines.append(f"completed_cards={len(list(payload.get('completed_card_ids') or []))}")
    return "\n".join(lines)


def _truncate_prompt_text(text: str, *, limit: int = 3600) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 80)].rstrip() + "\n\n...[preview truncated for prompt size]..."


def _orchestrate_continue_text(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip()
    stopped_reason = str(payload.get("stopped_reason") or "").strip()
    running_count = len(list(payload.get("running_card_ids") or []))
    ready_count = len(list(payload.get("ready_card_ids") or []))
    if status not in {"completed", "failed", "cancelled"} and (
        stopped_reason.startswith("waiting_on_") or running_count > 0 or ready_count > 0
    ):
        heading = "orchestration continue paused"
    else:
        heading = "orchestration continue finished"
    lines = [heading]
    lines.append(f"run_id={payload.get('run_id') or '-'}")
    lines.append(f"status={status or '-'}")
    lines.append(f"current_phase={payload.get('current_phase') or '-'}")
    lines.append(f"passes={payload.get('pass_count') or 0}")
    lines.append(f"max_passes={payload.get('max_passes') or payload.get('pass_count') or 0}")
    lines.append(f"stop_pass={payload.get('stop_pass') or payload.get('pass_count') or 0}")
    lines.append(f"mutated_passes={payload.get('mutated_pass_count') or 0}")
    lines.append(f"last_mutated_pass={payload.get('last_mutated_pass') or 0}")
    lines.append(f"stopped_reason={stopped_reason or '-'}")
    lines.append(f"pass_summaries={_render_continue_pass_summaries(payload)}")
    lines.append(
        "synced_cards=" + ",".join(str(item) for item in list(payload.get("synced_card_ids") or []))
        if payload.get("synced_card_ids")
        else "synced_cards=-"
    )
    lines.append(
        "accepted_cards="
        + ",".join(str(item) for item in list(payload.get("accepted_card_ids") or []))
        if payload.get("accepted_card_ids")
        else "accepted_cards=-"
    )
    lines.append(
        "unlocked_cards="
        + ",".join(str(item) for item in list(payload.get("unlocked_card_ids") or []))
        if payload.get("unlocked_card_ids")
        else "unlocked_cards=-"
    )
    lines.append(
        "selected_cards="
        + ",".join(str(item) for item in list(payload.get("selected_card_ids") or []))
        if payload.get("selected_card_ids")
        else "selected_cards=-"
    )
    lines.append(
        "dispatched_cards="
        + ",".join(str(item) for item in list(payload.get("dispatched_card_ids") or []))
        if payload.get("dispatched_card_ids")
        else "dispatched_cards=-"
    )
    lines.append(
        "dispatch_refs=" + ",".join(str(item) for item in list(payload.get("dispatch_refs") or []))
        if payload.get("dispatch_refs")
        else "dispatch_refs=-"
    )
    lines.append(f"ready_cards={len(list(payload.get('ready_card_ids') or []))}")
    lines.append(f"running_cards={len(list(payload.get('running_card_ids') or []))}")
    lines.append(f"blocked_cards={len(list(payload.get('blocked_card_ids') or []))}")
    lines.append(f"completed_cards={len(list(payload.get('completed_card_ids') or []))}")
    if heading.endswith("paused"):
        lines.append("next_action=wait for running cards, then run /orchestrate_continue again")
    return "\n".join(lines)


def _render_continue_pass_summaries(payload: dict[str, Any]) -> str:
    items = list(payload.get("pass_summaries") or [])
    if not items:
        return "-"
    rendered: list[str] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        pass_index = int(entry.get("pass") or 0)
        status = str(entry.get("status") or "").strip() or "-"
        phase = str(entry.get("current_phase") or "").strip() or "-"
        mutation = "mutated" if bool(entry.get("mutated")) else "noop"
        stop_candidate = str(entry.get("stop_candidate") or "").strip()
        fragment = f"{pass_index}:{status}/{phase}:{mutation}"
        if stop_candidate and stop_candidate != "continue":
            fragment += f":{stop_candidate}"
        rendered.append(fragment)
    if not rendered:
        return "-"
    return ";".join(rendered)


def _orchestrate_review_text(payload: dict[str, Any], *, applied: bool) -> str:
    card_id = str(payload.get("card_id") or "").strip()
    review_action = str(
        payload.get("review_action") or ("apply" if applied else "reject")
    ).strip() or ("apply" if applied else "reject")
    accepted_cards = [
        str(item) for item in list(payload.get("accepted_card_ids") or []) if str(item).strip()
    ]
    synced_cards = [
        str(item) for item in list(payload.get("synced_card_ids") or []) if str(item).strip()
    ]
    pending_review_cards = [item for item in synced_cards if item not in set(accepted_cards)]
    card_accepted = bool(card_id and card_id in set(accepted_cards))
    if review_action == "reject":
        card_acceptance_state = "rejected"
    elif card_accepted:
        card_acceptance_state = "accepted"
    elif card_id and card_id in set(pending_review_cards):
        card_acceptance_state = "pending_review"
    else:
        card_acceptance_state = "unknown"
    lines = [
        (
            "orchestration staged changes applied"
            if applied
            else "orchestration staged changes rejected"
        )
    ]
    lines.append(f"run_id={payload.get('run_id') or '-'}")
    lines.append(f"card_id={payload.get('card_id') or '-'}")
    lines.append(f"review_action={review_action}")
    lines.append(f"task_id={payload.get('task_id') or '-'}")
    lines.append(f"task_status={payload.get('task_status') or '-'}")
    lines.append(f"final_apply_state={payload.get('final_apply_state') or '-'}")
    lines.append(f"card_acceptance_state={card_acceptance_state}")
    lines.append(f"card_acceptance_applied={'true' if card_accepted else 'false'}")
    lines.append(f"review_pending_count={len(pending_review_cards)}")
    lines.append(
        "review_pending_cards=" + ",".join(pending_review_cards)
        if pending_review_cards
        else "review_pending_cards=-"
    )
    if payload.get("applied_files"):
        lines.append(
            "applied_files="
            + ",".join(str(item) for item in list(payload.get("applied_files") or []))
        )
    lines.append(f"status={payload.get('status') or '-'}")
    lines.append(f"current_phase={payload.get('current_phase') or '-'}")
    lines.append(
        "synced_cards=" + ",".join(str(item) for item in list(payload.get("synced_card_ids") or []))
        if payload.get("synced_card_ids")
        else "synced_cards=-"
    )
    lines.append(
        "accepted_cards="
        + ",".join(str(item) for item in list(payload.get("accepted_card_ids") or []))
        if payload.get("accepted_card_ids")
        else "accepted_cards=-"
    )
    lines.append(
        "unlocked_cards="
        + ",".join(str(item) for item in list(payload.get("unlocked_card_ids") or []))
        if payload.get("unlocked_card_ids")
        else "unlocked_cards=-"
    )
    lines.append(
        "selected_cards="
        + ",".join(str(item) for item in list(payload.get("selected_card_ids") or []))
        if payload.get("selected_card_ids")
        else "selected_cards=-"
    )
    lines.append(
        "dispatched_cards="
        + ",".join(str(item) for item in list(payload.get("dispatched_card_ids") or []))
        if payload.get("dispatched_card_ids")
        else "dispatched_cards=-"
    )
    lines.append(
        "dispatch_refs=" + ",".join(str(item) for item in list(payload.get("dispatch_refs") or []))
        if payload.get("dispatch_refs")
        else "dispatch_refs=-"
    )
    lines.append(f"ready_cards={len(list(payload.get('ready_card_ids') or []))}")
    lines.append(f"running_cards={len(list(payload.get('running_card_ids') or []))}")
    lines.append(f"blocked_cards={len(list(payload.get('blocked_card_ids') or []))}")
    lines.append(f"completed_cards={len(list(payload.get('completed_card_ids') or []))}")
    return "\n".join(lines)
