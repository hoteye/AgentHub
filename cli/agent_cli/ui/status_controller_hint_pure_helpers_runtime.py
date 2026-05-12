from __future__ import annotations

from typing import Any, Callable


def workflows_orchestration_review_hint(
    assistant_text: Any,
    *,
    tool_label_fn: Callable[[str], str],
    count_compact_fn: Callable[[Any], int],
    string_items_compact_fn: Callable[[Any], list[str]],
    card_ids_compact_fn: Callable[[Any], list[str]],
    preview_items_fn: Callable[[list[str]], str],
    operator_next_command_fn: Callable[[Any], str],
    orchestration_next_command_fn: Callable[..., str],
) -> str:
    lines = [str(raw_line or "").strip() for raw_line in str(assistant_text or "").splitlines()]
    for line in lines:
        if not line.startswith("- orchestration |"):
            continue
        parts = [str(part or "").strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        key_values: dict[str, str] = {}
        for token in parts[3:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            normalized_key = str(key or "").strip().lower()
            normalized_value = str(value or "").strip()
            if normalized_key:
                key_values[normalized_key] = normalized_value
        latest = (
            key_values.get("latest")
            or key_values.get("latest_acceptance")
            or key_values.get("acceptance")
            or key_values.get("decision")
            or ""
        )
        reason = (
            key_values.get("review_reason")
            or key_values.get("reason")
            or key_values.get("blocker")
            or ""
        )
        current = (
            key_values.get("current_result")
            or key_values.get("current")
            or key_values.get("result_hint")
            or key_values.get("latest_result")
            or ""
        )
        run_id = str(parts[1] or "").strip() if len(parts) > 1 else ""
        card_id = str((current or latest or "").split(":", 1)[0] or "").strip()
        next_op = orchestration_next_command_fn(
            run_id=run_id,
            card_id=card_id,
            review_action=key_values.get("review_action") or key_values.get("next_action") or "",
            phase=key_values.get("phase") or "",
            workflow_state=key_values.get("workflow") or "",
        )
        hints: list[str] = []
        if latest:
            hints.append(f"latest {tool_label_fn(latest)}")
        if reason:
            hints.append(f"review {tool_label_fn(reason)}")
        if current:
            hints.append(f"current {tool_label_fn(current)}")
        replan_candidates = count_compact_fn(key_values.get("replan_candidates"))
        if replan_candidates > 0:
            hints.append(f"replan candidates {replan_candidates}")
        replan_pending = count_compact_fn(key_values.get("replan_pending"))
        if replan_pending > 0:
            hints.append(f"replan pending {replan_pending}")
        replan_cards = string_items_compact_fn(key_values.get("replan_pending_card_ids"))
        if not replan_cards:
            replan_cards = card_ids_compact_fn(key_values.get("replan_pending"))
        if not replan_cards:
            replan_cards = card_ids_compact_fn(key_values.get("replan_candidates"))
        if replan_cards:
            hints.append(f"replan cards {tool_label_fn(preview_items_fn(replan_cards))}")
        operator_actions = count_compact_fn(key_values.get("operator_actions"))
        if operator_actions > 0:
            hints.append(f"operator actions {operator_actions}")
        operator_next = operator_next_command_fn(key_values.get("operator_actions"))
        if operator_next:
            hints.append(f"next {tool_label_fn(operator_next)}")
        if next_op:
            hints.append(f"next {tool_label_fn(next_op)}")
        if hints:
            return " · ".join(hints)
    return ""


def workflows_command_hint(
    *,
    key_values: dict[str, str],
    normalized_count_fn: Callable[[Any], str],
    flag_label_fn: Callable[[str], str],
    result_contract_hint: str,
    review_hint: str,
    execution_projection_hint: str,
) -> str:
    total = normalized_count_fn(key_values.get("workflows"))
    delegated = normalized_count_fn(key_values.get("delegated_workflows"))
    orchestration = normalized_count_fn(key_values.get("orchestration_runs"))
    orchestration_ready = normalized_count_fn(key_values.get("orchestration_ready"))
    background = normalized_count_fn(key_values.get("background_tasks"))
    mirrored = normalized_count_fn(key_values.get("mirrored_background_tasks"))
    enabled = str(key_values.get("background_tasks_enabled") or "").strip()
    parts = [f"workflows {total if total != '-' else '?'}"]
    if delegated != "-":
        parts.append(f"delegated {delegated}")
    if orchestration not in {"-", "0"}:
        parts.append(f"orchestration {orchestration}")
    if orchestration_ready not in {"-", "0"}:
        parts.append(f"ready {orchestration_ready}")
    if background != "-":
        parts.append(f"background {background}")
    if mirrored not in {"-", "0"}:
        parts.append(f"mirrored {mirrored}")
    if enabled not in {"", "-"}:
        parts.append(f"queue {flag_label_fn(enabled)}")
    if result_contract_hint:
        parts.append(result_contract_hint)
    if review_hint:
        parts.append(review_hint)
    if execution_projection_hint:
        parts.append(execution_projection_hint)
    return " · ".join(parts)


def background_tasks_command_hint(
    *,
    key_values: dict[str, str],
    normalized_count_fn: Callable[[Any], str],
    tool_label_fn: Callable[[str], str],
    flag_label_fn: Callable[[str], str],
) -> str:
    total = normalized_count_fn(key_values.get("background_tasks"))
    worker_health = str(key_values.get("background_worker_health") or "").strip()
    worker_status = str(key_values.get("background_worker_status") or "").strip()
    worker_mode = str(key_values.get("background_worker_mode") or "").strip()
    enabled = str(key_values.get("background_tasks_enabled") or "").strip()
    parts = [f"background tasks {total if total != '-' else '?'}"]
    worker_parts = [
        tool_label_fn(item) for item in (worker_health, worker_status) if item not in {"", "-"}
    ]
    if worker_parts:
        parts.append("worker " + "/".join(worker_parts[:2]))
    if worker_mode not in {"", "-"}:
        parts.append(f"mode {tool_label_fn(worker_mode)}")
    if enabled not in {"", "-"}:
        parts.append(f"enabled {flag_label_fn(enabled)}")
    return " · ".join(parts)


def background_worker_status_command_hint(
    *,
    key_values: dict[str, str],
    tool_label_fn: Callable[[str], str],
) -> str:
    health = str(key_values.get("health") or "").strip()
    status = str(key_values.get("status") or "").strip()
    mode = str(key_values.get("mode") or "").strip()
    worker_pid = str(key_values.get("worker_pid") or "").strip()
    restart_required = str(key_values.get("restart_required") or "").strip().lower()
    version_match = str(key_values.get("worker_code_version_match") or "").strip().lower()
    worker_code_version = str(key_values.get("worker_code_version") or "").strip()
    current_worker_code_version = str(key_values.get("current_worker_code_version") or "").strip()
    active_task_id = str(key_values.get("active_task_id") or "").strip()
    active_task_type = str(key_values.get("active_task_type") or "").strip()
    stop_reason = str(key_values.get("stop_reason") or key_values.get("reason") or "").strip()
    parts = ["worker"]
    if health not in {"", "-"}:
        parts.append(tool_label_fn(health))
    if status not in {"", "-", health}:
        parts.append(tool_label_fn(status))
    if mode not in {"", "-"}:
        parts.append(f"mode {tool_label_fn(mode)}")
    if worker_pid not in {"", "-"}:
        parts.append(f"pid {worker_pid}")
    if active_task_id not in {"", "-"}:
        active_label = active_task_id
        if active_task_type not in {"", "-"}:
            active_label += f":{active_task_type}"
        parts.append(f"active {tool_label_fn(active_label)}")
    mismatch = False
    if restart_required == "true":
        mismatch = True
    elif version_match == "false":
        mismatch = True
    elif (
        worker_code_version not in {"", "-"}
        and current_worker_code_version not in {"", "-"}
        and worker_code_version != current_worker_code_version
    ):
        mismatch = True
    if mismatch:
        parts.append("restart required")
    if stop_reason not in {"", "-"}:
        parts.append(f"stop {tool_label_fn(stop_reason)}")
    return " · ".join(parts)


def background_worker_run_once_command_hint(
    *,
    key_values: dict[str, str],
    assistant_text: Any,
    normalized_count_fn: Callable[[Any], str],
    tool_label_fn: Callable[[str], str],
    operator_hint_title_fn: Callable[[Any], str],
) -> str:
    title = operator_hint_title_fn(assistant_text) or "background worker run once completed"
    processed = normalized_count_fn(key_values.get("processed"))
    health = str(key_values.get("health") or "").strip()
    status = str(key_values.get("status") or "").strip()
    parts = [tool_label_fn(title.replace("background ", ""))]
    if processed != "-":
        parts.append(f"processed {processed}")
    if health not in {"", "-"}:
        parts.append(tool_label_fn(health))
    if status not in {"", "-", health}:
        parts.append(tool_label_fn(status))
    return " · ".join(parts)


def background_worker_lifecycle_command_hint(
    *,
    key_values: dict[str, str],
    assistant_text: Any,
    tool_label_fn: Callable[[str], str],
    operator_hint_title_fn: Callable[[Any], str],
) -> str:
    title = operator_hint_title_fn(assistant_text)
    if not title:
        return ""
    worker_pid = str(key_values.get("worker_pid") or "").strip()
    reason = str(key_values.get("reason") or "").strip()
    parts = [tool_label_fn(title.replace("background ", ""))]
    if worker_pid not in {"", "-"}:
        parts.append(f"pid {worker_pid}")
    if reason not in {"", "-"}:
        parts.append(reason)
    return " · ".join(parts)
