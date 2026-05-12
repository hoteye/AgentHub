from __future__ import annotations

import hashlib
from typing import Any

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun, TaskCardState
from cli.agent_cli.orchestration.taskbook_state import CardResultStatus


def selector_value(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"", "-", "inherit"}:
        return ""
    return text


def taskbook_summary_label(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    version = int(view.get("taskbook_version_current") or run.taskbook_version_current or 0)
    accepted_facts = [selector_value(item) for item in list(view.get("accepted_facts") or [])]
    accepted_fact_count = len([item for item in accepted_facts if item])
    if version <= 0 and accepted_fact_count <= 0:
        return ""
    return f"v{max(0, version)},facts={accepted_fact_count}"


def projection_summary_label(view: dict[str, Any]) -> str:
    accepted = 0
    pending_review = 0
    rework = 0
    blocked = 0
    failed = 0
    cards = [dict(item) for item in list(view.get("cards") or []) if isinstance(item, dict)]
    if not cards:
        return ""
    for card in cards:
        latest_result = card.get("latest_result")
        latest_acceptance = card.get("latest_acceptance")
        if isinstance(latest_result, dict):
            result_status = selector_value(latest_result.get("status"))
            if result_status in {"failed", "timed_out", "cancelled"}:
                failed += 1
            if not isinstance(latest_acceptance, dict):
                pending_review += 1
        decision = selector_value(latest_acceptance.get("decision")) if isinstance(latest_acceptance, dict) else ""
        if decision == "accept":
            accepted += 1
        elif decision == "rework":
            rework += 1
        elif decision in {"block", "reject"}:
            blocked += 1
    return f"accept={accepted},pending={pending_review},rework={rework},blocked={blocked},failed={failed}"


def current_card_label(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    cards = {str(item.get("card_id") or ""): dict(item) for item in list(view.get("cards") or []) if isinstance(item, dict)}
    for card_id in list(run.running_card_ids or []):
        if card_id in cards:
            return f"{card_id}:{cards[card_id].get('status') or 'running'}"
    for card_id in list(run.ready_card_ids or []):
        if card_id in cards:
            return f"{card_id}:{cards[card_id].get('status') or 'ready'}"
    for card_id in list(run.blocked_card_ids or []):
        if card_id in cards:
            return f"{card_id}:{cards[card_id].get('status') or 'blocked'}"
    return ""


def blocker_label(view: dict[str, Any]) -> str:
    for item in list(view.get("cards") or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        decision = str(item.get("last_scheduler_decision") or "").strip()
        if status not in {"blocked", "rework", "failed", "cancelled", "draft"}:
            continue
        card_id = str(item.get("card_id") or "").strip()
        if card_id and decision:
            return f"{card_id}:{decision}"
        if card_id:
            return f"{card_id}:{status}"
    return ""


def latest_outcome_label(view: dict[str, Any]) -> str:
    latest_at = ""
    latest_label = ""
    for item in list(view.get("cards") or []):
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("card_id") or "").strip()
        acceptance = item.get("latest_acceptance")
        result = item.get("latest_result")
        if isinstance(acceptance, dict):
            reviewed_at = selector_value(acceptance.get("reviewed_at"))
            decision = selector_value(acceptance.get("decision"))
            if reviewed_at >= latest_at and card_id and decision:
                latest_at = reviewed_at
                latest_label = f"{card_id}:acceptance:{decision}"
        if isinstance(result, dict):
            reported_at = selector_value(result.get("reported_at"))
            status = selector_value(result.get("status"))
            if reported_at >= latest_at and card_id and status:
                latest_at = reported_at
                latest_label = f"{card_id}:result:{status}"
    return latest_label


def latest_acceptance_label(view: dict[str, Any]) -> str:
    latest_at = ""
    latest_label = ""
    for item in list(view.get("cards") or []):
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("card_id") or "").strip()
        acceptance = item.get("latest_acceptance")
        if not isinstance(acceptance, dict):
            continue
        reviewed_at = selector_value(acceptance.get("reviewed_at"))
        decision = selector_value(acceptance.get("decision"))
        if reviewed_at >= latest_at and card_id and decision:
            latest_at = reviewed_at
            latest_label = f"{card_id}:{decision}"
    return latest_label


def review_reason_label(view: dict[str, Any]) -> str:
    for item in list(view.get("cards") or []):
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("card_id") or "").strip()
        if not card_id:
            continue
        status = str(item.get("status") or "").strip()
        if status not in {"blocked", "review", "rework", "failed", "cancelled"}:
            continue
        acceptance = item.get("latest_acceptance")
        if isinstance(acceptance, dict):
            reason = selector_value(acceptance.get("reason"))
            if reason:
                return f"{card_id}:{reason}"
        latest_result = item.get("latest_result")
        if isinstance(latest_result, dict):
            reason = selector_value(latest_result.get("suggested_next_action")) or selector_value(
                latest_result.get("summary")
            )
            if reason:
                return f"{card_id}:{reason}"
    return ""


def current_card_latest_result_hint(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    cards = {str(item.get("card_id") or ""): dict(item) for item in list(view.get("cards") or []) if isinstance(item, dict)}
    current_card_id = ""
    for card_id in list(run.running_card_ids or []):
        if card_id in cards:
            current_card_id = card_id
            break
    if not current_card_id:
        for card_id in list(run.blocked_card_ids or []):
            if card_id in cards:
                current_card_id = card_id
                break
    if not current_card_id:
        return ""
    latest_result = cards[current_card_id].get("latest_result")
    if not isinstance(latest_result, dict):
        return ""
    status = selector_value(latest_result.get("status")) or "-"
    summary = selector_value(latest_result.get("summary")) or selector_value(latest_result.get("suggested_next_action"))
    if not summary:
        return f"{current_card_id}:{status}"
    compact_summary = summary if len(summary) <= 32 else summary[:29] + "..."
    return f"{current_card_id}:{status}:{compact_summary}"


def workflow_line(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    taskbook = taskbook_summary_label(run, view)
    projection = projection_summary_label(view)
    current = current_card_label(run, view)
    blocker = blocker_label(view)
    latest = latest_outcome_label(view)
    latest_acceptance = latest_acceptance_label(view)
    review_reason = review_reason_label(view)
    current_result = current_card_latest_result_hint(run, view)
    segments = [
        "orchestration",
        run.run_id,
        run.status.value,
        f"workflow={run.status.value}",
        f"phase={run.current_phase or '-'}",
        f"cards={len(list(view.get('cards') or []))}",
        f"ready={len(list(run.ready_card_ids or []))}",
        f"running={len(list(run.running_card_ids or []))}",
        f"blocked={len(list(run.blocked_card_ids or []))}",
        f"accepted={len(list(run.completed_card_ids or []))}",
    ]
    if taskbook:
        segments.append(f"taskbook={taskbook}")
    if projection:
        segments.append(f"projection={projection}")
    if blocker:
        segments.append(f"blocker={blocker}")
    if latest:
        segments.append(f"latest={latest}")
    if latest_acceptance:
        segments.append(f"latest_acceptance={latest_acceptance}")
    if review_reason:
        segments.append(f"review_reason={review_reason}")
    if current_result:
        segments.append(f"current_result={current_result}")
    if current:
        segments.append(f"current={current}")
    return "- " + " | ".join(segments)


def dispatch_ref_label(card_id: str, state: TaskCardState) -> str:
    refs = list(state.execution_refs or [])
    if not refs:
        return str(card_id or "").strip()
    ref = refs[-1]
    identifier = str(ref.task_id or ref.agent_id or "").strip() or "-"
    return f"{str(card_id or '').strip()}:{ref.kind.value}:{identifier}"


def result_id(card_id: str, attempt: int, execution_ref: Any, fingerprint: str) -> str:
    raw = "|".join(
        [
            str(card_id or ""),
            str(attempt or 0),
            execution_ref.kind.value,
            str(execution_ref.task_id or ""),
            str(execution_ref.agent_id or ""),
            str(fingerprint or ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"result_{str(card_id or '').lower()}_{digest}"


def acceptance_id(card_id: str, result_id_value: str, decision: str) -> str:
    digest = hashlib.sha1(f"{card_id}|{result_id_value}|{decision}".encode("utf-8")).hexdigest()[:12]
    return f"accept_{str(card_id or '').lower()}_{digest}"


def string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item or "").strip()]
    if str(value or "").strip():
        return [str(value)]
    return []


def looks_like_taskbook_markdown(text: str) -> bool:
    stripped = str(text or "").strip()
    return stripped.startswith("# ") or "\n### " in stripped


def looks_like_checklist(text: str) -> bool:
    normalized = str(text or "")
    return "- [ ]" in normalized or "- [x]" in normalized or "- [X]" in normalized


def test_commands(commands: list[str]) -> list[str]:
    test_markers = (
        "pytest",
        "python -m pytest",
        "unittest",
        "python -m unittest",
        "npm test",
        "pnpm test",
        "yarn test",
        "vitest",
        "jest",
        "go test",
        "cargo test",
    )
    return [command for command in commands if any(marker in command for marker in test_markers)]


def result_reported_at(payload: dict[str, Any], *, utc_now_iso_fn: Any) -> str:
    result_payload = payload.get("result")
    if isinstance(result_payload, dict):
        finished_at = selector_value(result_payload.get("finished_at"))
        if finished_at:
            return finished_at
        started_at = selector_value(result_payload.get("started_at"))
        if started_at:
            return started_at
    return utc_now_iso_fn()


def delegated_terminal_result_status(snapshot: dict[str, Any], *, result_contract: dict[str, Any]) -> CardResultStatus | None:
    status = selector_value(result_contract.get("status")) or selector_value(snapshot.get("status"))
    terminal_state = selector_value(snapshot.get("terminal_state"))
    terminal_reason = selector_value(snapshot.get("terminal_reason"))
    if status in {"", "queued", "starting", "running", "closing"}:
        return None
    if status == "completed":
        return CardResultStatus.COMPLETED
    if status == "failed":
        return CardResultStatus.FAILED
    if status == "cancelled":
        return CardResultStatus.CANCELLED
    if status == "closed":
        if terminal_state == "timed_out" or terminal_reason == "timeout":
            return CardResultStatus.TIMED_OUT
        return CardResultStatus.CANCELLED
    if terminal_state == "timed_out":
        return CardResultStatus.TIMED_OUT
    if terminal_state == "cancelled":
        return CardResultStatus.CANCELLED
    return None


def background_terminal_result_status(payload: dict[str, Any], *, artifact: dict[str, Any]) -> CardResultStatus | None:
    status = selector_value(payload.get("status"))
    if status in {"", "queued", "running", "starting", "unknown"}:
        return None
    terminal_state = selector_value(artifact.get("terminal_state"))
    if terminal_state == "timed_out":
        return CardResultStatus.TIMED_OUT
    if status == "completed":
        return CardResultStatus.COMPLETED
    if status == "cancelled" or terminal_state == "cancelled":
        return CardResultStatus.CANCELLED
    if status == "failed":
        return CardResultStatus.FAILED
    return None
