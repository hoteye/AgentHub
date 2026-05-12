from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration.taskbook_models import ExecutionRef, TaskCard
from cli.agent_cli.orchestration.taskbook_projection_runtime import (
    normalize_join_next_action,
    normalize_join_result_state,
    normalize_join_summary,
)
from cli.agent_cli.orchestration.taskbook_state import CardResultStatus, TaskCardKind


def relative_paths(root: Path, value: Any, *, string_list_fn: Any) -> list[str]:
    items = string_list_fn(value)
    relative: list[str] = []
    for item in items:
        path = Path(item).expanduser()
        try:
            normalized = path.resolve(strict=False) if path.is_absolute() else (root / path).resolve(strict=False)
        except OSError:
            normalized = path if path.is_absolute() else root / path
        try:
            relative_path = normalized.relative_to(root)
            text = relative_path.as_posix()
        except ValueError:
            text = normalized.as_posix()
        if text and text not in relative:
            relative.append(text)
    return relative


def delegated_commands(snapshot: dict[str, Any], *, selector_value_fn: Any) -> list[str]:
    commands: list[str] = []
    for item in list(snapshot.get("last_tool_events") or []):
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        command = selector_value_fn(payload.get("command")) or selector_value_fn(payload.get("effective_command"))
        if command and command not in commands:
            commands.append(command)
    return commands


def delegated_result_parts(
    *,
    card: TaskCard,
    execution_ref: ExecutionRef,
    snapshot: dict[str, Any],
    result_contract: dict[str, Any],
    terminal_status: CardResultStatus,
    root: Path,
    string_list_fn: Any,
    selector_value_fn: Any,
    relative_paths_fn: Any = relative_paths,
    delegated_commands_fn: Any = delegated_commands,
    normalize_join_result_state_fn: Any = normalize_join_result_state,
    normalize_join_next_action_fn: Any = normalize_join_next_action,
    normalize_join_summary_fn: Any = normalize_join_summary,
) -> dict[str, Any]:
    raw_summary = (
        selector_value_fn(result_contract.get("summary"))
        or selector_value_fn(snapshot.get("text"))
        or selector_value_fn(snapshot.get("error"))
        or terminal_status.value
    )
    completion_state = selector_value_fn(snapshot.get("completion_state")) or selector_value_fn(
        result_contract.get("completion_state")
    )
    result_state = normalize_join_result_state_fn(
        terminal_status=terminal_status.value,
        completion_state=completion_state,
        next_action=selector_value_fn(result_contract.get("next_action")),
        adopted=bool(snapshot.get("adopted")),
    )
    next_action = normalize_join_next_action_fn(
        next_action=selector_value_fn(result_contract.get("next_action")),
        result_state=result_state,
        completion_state=completion_state,
    )
    summary = normalize_join_summary_fn(
        summary=raw_summary,
        result_state=result_state,
        terminal_status=terminal_status.value,
    )
    touched_scope = relative_paths_fn(root, result_contract.get("touched_scope"), string_list_fn=string_list_fn)
    commands = delegated_commands_fn(snapshot, selector_value_fn=selector_value_fn)
    risks = string_list_fn(snapshot.get("warnings")) or string_list_fn(result_contract.get("warnings"))
    blockers: list[str] = []
    error_text = selector_value_fn(snapshot.get("error"))
    if error_text:
        blockers.append(error_text)
    if result_state == "blocked" and next_action and next_action not in {"manual_review_required"} and next_action not in blockers:
        blockers.append(next_action)

    needs_review = bool(touched_scope) or card.kind is not TaskCardKind.READ_ONLY
    if result_state in {"pending_review", "blocked"}:
        needs_review = True
    fingerprint = "|".join(
        [
            terminal_status.value,
            completion_state,
            result_state,
            next_action,
            selector_value_fn(snapshot.get("terminal_state")),
            selector_value_fn(snapshot.get("terminal_reason")),
            summary,
            ",".join(touched_scope),
        ]
    )
    return {
        "summary": summary,
        "modified_files": touched_scope,
        "commands": commands,
        "risks": risks,
        "blockers": blockers,
        "needs_review": needs_review,
        "result_state": result_state,
        "completion_state": completion_state,
        "suggested_next_action": next_action,
        "fingerprint": fingerprint,
        "artifacts": [
            {
                "kind": "delegated_snapshot",
                "agent_id": execution_ref.agent_id,
                "status": str(snapshot.get("status") or ""),
                "terminal_state": str(snapshot.get("terminal_state") or ""),
                "completion_state": str(snapshot.get("completion_state") or ""),
                "result_state": result_state,
                "next_action": next_action,
                "result_contract": result_contract,
            }
        ],
    }


def background_result_parts(
    payload: dict[str, Any],
    *,
    execution_ref: ExecutionRef,
    artifact: dict[str, Any],
    terminal_status: CardResultStatus,
    string_list_fn: Any,
    selector_value_fn: Any,
    normalize_join_result_state_fn: Any = normalize_join_result_state,
    normalize_join_next_action_fn: Any = normalize_join_next_action,
    normalize_join_summary_fn: Any = normalize_join_summary,
) -> dict[str, Any]:
    final_apply_state = selector_value_fn(artifact.get("final_apply_state"))
    final_apply_pending = bool(artifact.get("final_apply_pending"))
    effective_status = CardResultStatus.CANCELLED if final_apply_state == "rejected" else terminal_status
    modified_files = string_list_fn(artifact.get("modified_files"))
    commands = string_list_fn(artifact.get("commands"))
    test_command_values = string_list_fn(artifact.get("test_commands"))
    out_of_scope_files = string_list_fn(artifact.get("out_of_scope_files"))
    completion_state = selector_value_fn(payload.get("completion_state")) or selector_value_fn(artifact.get("completion_state"))
    notification_state = selector_value_fn(artifact.get("notification_state"))
    adoption_expectation = selector_value_fn(payload.get("adoption_expectation")) or selector_value_fn(
        artifact.get("adoption_expectation")
    )
    result_state = normalize_join_result_state_fn(
        terminal_status=effective_status.value,
        explicit_state=selector_value_fn(payload.get("result_state")) or selector_value_fn(artifact.get("result_state")),
        completion_state=completion_state,
        next_action=adoption_expectation,
        adopted=bool(notification_state == "foreground_adopted" or completion_state == "adopted"),
        final_apply_state=final_apply_state,
        final_apply_pending=final_apply_pending,
        notification_state=notification_state,
    )
    next_action = normalize_join_next_action_fn(
        next_action=adoption_expectation,
        result_state=result_state,
        completion_state=completion_state,
    )
    blockers: list[str] = []
    error_text = selector_value_fn(payload.get("error"))
    if error_text:
        blockers.append(error_text)
    if out_of_scope_files:
        blockers.append("out_of_scope_files: " + ", ".join(out_of_scope_files))
    if final_apply_state == "blocked":
        blockers.append("final_apply_blocked")
    if result_state == "blocked" and next_action and next_action not in {"manual_review_required"} and next_action not in blockers:
        blockers.append(next_action)
    needs_review = result_state in {"pending_review", "blocked"} or bool(out_of_scope_files)
    summary = normalize_join_summary_fn(
        summary=selector_value_fn(payload.get("summary")) or effective_status.value,
        result_state=result_state,
        terminal_status=effective_status.value,
    )
    fingerprint = "|".join(
        [
            effective_status.value,
            selector_value_fn(payload.get("status")),
            selector_value_fn(artifact.get("terminal_state")),
            final_apply_state,
            result_state,
            completion_state,
            next_action,
            summary,
            ",".join(modified_files),
        ]
    )
    return {
        "terminal_status": effective_status,
        "summary": summary,
        "modified_files": modified_files,
        "commands": commands,
        "test_commands": test_command_values,
        "blockers": blockers,
        "needs_review": needs_review,
        "result_state": result_state,
        "completion_state": completion_state,
        "suggested_next_action": next_action,
        "fingerprint": fingerprint,
        "artifacts": [
            {
                "kind": "background_task",
                "task_id": execution_ref.task_id,
                "status": str(payload.get("status") or ""),
                "terminal_state": str(artifact.get("terminal_state") or ""),
                "result_state": result_state,
                "completion_state": completion_state,
                "next_action": next_action,
                "snapshot_path": str(artifact.get("snapshot_path") or ""),
                "response_path": str(artifact.get("response_path") or ""),
                "review_path": str(artifact.get("review_path") or ""),
                "report_path": str(artifact.get("report_path") or ""),
            }
        ],
        "risks": string_list_fn(artifact.get("review_commands")),
    }
