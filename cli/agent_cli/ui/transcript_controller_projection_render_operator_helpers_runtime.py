from __future__ import annotations

from typing import Any, Callable


def operator_workflow_detail_lines(
    assistant_text: str,
    *,
    operator_pipe_segments_fn: Callable[[str], list[str]],
    operator_segment_map_fn: Callable[[list[str]], tuple[list[str], dict[str, str]]],
    workflow_detail_identity_fn: Callable[[dict[str, str]], tuple[str, str, str]],
    workflow_next_op_fn: Callable[..., str],
    workflow_nested_value_fn: Callable[[dict[str, str], str], Any],
    count_compact_fn: Callable[[Any], int],
    string_items_compact_fn: Callable[[Any], list[str]],
    card_ids_compact_fn: Callable[[Any], list[str]],
    preview_items_fn: Callable[[list[str]], str],
    operator_next_command_fn: Callable[[Any], str],
    followup_summary_fn: Callable[[Any], tuple[int, str, str]],
    policy_surface_fn: Callable[[Any], str],
) -> list[str]:
    lines: list[str] = []
    for raw_line in str(assistant_text or "").splitlines():
        segments = operator_pipe_segments_fn(raw_line)
        if not segments:
            continue
        positional, keyed = operator_segment_map_fn(segments)
        if len(positional) < 3:
            continue
        workflow_type = positional[0]
        identifier = positional[1]
        status = positional[2]
        parts = [f"{workflow_type} {identifier} {status}"]
        label_by_key = {
            "run": "run",
            "card": "card",
            "task": "task",
            "action": "action",
            "role": "role",
            "workflow": "workflow",
            "phase": "phase",
            "cards": "cards",
            "ready": "ready",
            "running": "running",
            "blocked": "blocked",
            "accepted": "accepted",
            "completion": "completion",
            "terminal_state": "terminal state",
            "next": "next",
            "wait": "wait",
            "current": "current",
            "current_result": "current result",
            "blocker": "blocker",
            "latest": "latest",
            "latest_acceptance": "acceptance",
            "taskbook": "taskbook",
            "projection": "projection",
            "review_reason": "review",
            "review_card": "review card",
            "review_action": "review action",
            "dispatch_ref": "dispatch ref",
            "dispatch_refs": "dispatch refs",
            "execution_ref": "execution ref",
            "execution_refs": "execution refs",
            "result_ref": "result ref",
            "result_id": "result id",
            "workflow_action": "workflow action",
            "next_action": "next action",
            "policy": "policy",
            "policy_state": "policy",
            "policy_reason": "policy reason",
            "command_policy_surface": "policy",
            "policy_denied": "policy denied",
            "policy_rewrite": "policy rewrite",
            "policy_checked": "policy checked",
            "command_policies_count": "policy checked",
        }
        for key in (
            "run",
            "card",
            "task",
            "action",
            "role",
            "workflow",
            "phase",
            "cards",
            "ready",
            "running",
            "blocked",
            "accepted",
            "completion",
            "terminal_state",
            "next",
            "wait",
            "taskbook",
            "projection",
            "current",
            "current_result",
            "blocker",
            "latest",
            "latest_acceptance",
            "review_reason",
            "review_card",
            "review_action",
            "dispatch_ref",
            "dispatch_refs",
            "execution_ref",
            "execution_refs",
            "result_ref",
            "result_id",
            "workflow_action",
            "next_action",
            "policy",
            "policy_state",
            "policy_reason",
            "command_policy_surface",
            "policy_denied",
            "policy_rewrite",
            "policy_checked",
            "command_policies_count",
        ):
            value = str(keyed.get(key) or "").strip()
            if value:
                parts.append(f"{label_by_key.get(key, key.replace('_', ' '))} {value}")
        run_id = str(keyed.get("run") or "").strip()
        if not run_id:
            run_id = identifier
        card_id, task_id, action_name = workflow_detail_identity_fn(keyed)
        if run_id and not str(keyed.get("run") or "").strip():
            parts.append(f"run {run_id}")
        if card_id and not str(keyed.get("card") or "").strip():
            parts.append(f"card {card_id}")
        if task_id and not str(keyed.get("task") or "").strip():
            parts.append(f"task {task_id}")
        if action_name and not str(keyed.get("action") or "").strip():
            parts.append(f"action {action_name}")
        next_op = workflow_next_op_fn(
            workflow_type=workflow_type,
            run_id=run_id,
            card_id=card_id,
            task_id=task_id,
            action_name=action_name,
            workflow_state=str(keyed.get("workflow") or "").strip(),
            phase=str(keyed.get("phase") or "").strip(),
            status=status,
        )
        if next_op:
            parts.append(f"next op {next_op}")
        replan_candidates_value = workflow_nested_value_fn(keyed, "replan_candidates")
        replan_candidates_count = count_compact_fn(replan_candidates_value)
        if replan_candidates_count > 0:
            parts.append(f"replan candidates {replan_candidates_count}")
        replan_pending_value = workflow_nested_value_fn(keyed, "replan_pending")
        replan_pending_count = count_compact_fn(replan_pending_value)
        if replan_pending_count > 0:
            parts.append(f"replan pending {replan_pending_count}")
        replan_cards = string_items_compact_fn(workflow_nested_value_fn(keyed, "replan_pending_card_ids"))
        if not replan_cards:
            replan_cards = card_ids_compact_fn(replan_pending_value)
        if not replan_cards:
            replan_cards = card_ids_compact_fn(replan_candidates_value)
        if replan_cards:
            parts.append(f"replan cards {preview_items_fn(replan_cards)}")
        operator_actions_value = workflow_nested_value_fn(keyed, "operator_actions")
        operator_actions_count = count_compact_fn(operator_actions_value)
        if operator_actions_count > 0:
            parts.append(f"operator actions {operator_actions_count}")
        operator_next = operator_next_command_fn(operator_actions_value)
        if operator_next:
            parts.append(f"operator next {operator_next}")
        followup_actions_value = workflow_nested_value_fn(keyed, "replan_followup_actions")
        followup_count, followup_scopes, followup_triggers = followup_summary_fn(followup_actions_value)
        if followup_count > 0:
            parts.append(f"replan followup {followup_count}")
            if followup_scopes:
                parts.append(f"replan scope {followup_scopes}")
            if followup_triggers:
                parts.append(f"replan trigger {followup_triggers}")
        command_policies = str(keyed.get("command_policies") or "").strip()
        policy_surface_value = policy_surface_fn(command_policies)
        if policy_surface_value:
            parts.append(policy_surface_value)
        summary = ""
        if workflow_type == "background" and len(positional) >= 4:
            summary = str(positional[3] or "").strip()
        if summary and summary != "-":
            parts.append(summary)
        lines.append(" · ".join(parts))
    return lines


def operator_background_task_detail_lines(
    assistant_text: str,
    *,
    operator_pipe_segments_fn: Callable[[str], list[str]],
    operator_segment_map_fn: Callable[[list[str]], tuple[list[str], dict[str, str]]],
    policy_surface_fn: Callable[[Any], str],
) -> list[str]:
    lines: list[str] = []
    for raw_line in str(assistant_text or "").splitlines():
        segments = operator_pipe_segments_fn(raw_line)
        if not segments:
            continue
        positional, keyed = operator_segment_map_fn(segments)
        if len(positional) < 3:
            continue
        task_id = positional[0]
        status = positional[1]
        summary = positional[2]
        parts = [f"task {task_id} {status}"]
        if summary and summary != "-":
            parts.append(summary)
        for key in (
            "type",
            "workflow",
            "terminal_state",
            "terminal",
            "review",
            "wait",
            "current",
            "notify",
            "policy",
            "policy_state",
            "command_policy_surface",
            "policy_denied",
            "policy_rewrite",
            "policy_checked",
            "command_policies_count",
        ):
            value = str(keyed.get(key) or "").strip()
            if value:
                parts.append(f"{key.replace('_', ' ')} {value}")
        command_policies = str(keyed.get("command_policies") or "").strip()
        policy_surface_value = policy_surface_fn(command_policies)
        if policy_surface_value:
            parts.append(policy_surface_value)
        lines.append(" · ".join(parts))
    return lines


def single_operator_detail_line(
    command_name: str,
    key_values: dict[str, str],
    *,
    policy_surface_fn: Callable[[Any], str],
) -> str:
    subject = ""
    if command_name.startswith("background_task"):
        task_id = str(key_values.get("task_id") or "").strip()
        status = str(key_values.get("status") or "").strip()
        if task_id:
            subject = f"task {task_id}"
            if status:
                subject += f" {status}"
    else:
        agent_id = str(key_values.get("agent_id") or "").strip()
        status = str(key_values.get("status") or "").strip()
        if agent_id:
            subject = f"agent {agent_id}"
            if status:
                subject += f" {status}"
    if not subject:
        return ""
    parts = [subject]
    for key in ("workflow_state", "completion_state", "adoption_expectation", "terminal_state", "final_apply_state"):
        value = str(key_values.get(key) or "").strip()
        if value:
            parts.append(f"{key.replace('_', ' ')} {value}")
    policy_surface_value = str(key_values.get("command_policy_surface") or "").strip()
    if not policy_surface_value:
        policy_surface_value = policy_surface_fn(key_values.get("command_policies"))
    if policy_surface_value:
        parts.append(policy_surface_value)
    for key in ("scheduler_reason", "terminal_reason", "summary"):
        value = str(key_values.get(key) or "").strip()
        if value:
            parts.append(value)
            break
    return " · ".join(parts)
