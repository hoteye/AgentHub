from __future__ import annotations

from pathlib import Path
from typing import Any

from . import tasks_execution_runtime
from . import tasks_flow_runtime
from .models import TaskResult, utc_now_iso
from .storage import BackgroundTaskStorage


def apply_staged_teammate_result(
    task_id: str,
    *,
    storage: BackgroundTaskStorage,
    load_review_payload_fn: Any,
    normalize_policy_path_fn: Any,
    parse_path_list_fn: Any,
    dedupe_compact_items_fn: Any,
    paths_outside_policy_fn: Any,
    trim_error_fn: Any,
    persist_updated_result_fn: Any,
) -> TaskResult | None:
    current = storage.get_result(task_id)
    if current is None:
        return None
    artifact = dict(current.artifact or {})
    if not artifact.get("staged_workspace") or not artifact.get("final_apply_pending"):
        return current
    review_payload = load_review_payload_fn(artifact.get("review_path"))
    live_cwd = Path(str(review_payload.get("live_cwd") or artifact.get("live_cwd") or "")).expanduser().resolve()
    stage_cwd = Path(str(review_payload.get("stage_cwd") or artifact.get("stage_cwd") or "")).expanduser().resolve()
    review_state = tasks_flow_runtime.staged_review_state(
        task_id=task_id,
        artifact=artifact,
        review_payload=review_payload,
        live_cwd=live_cwd,
        normalize_policy_path_fn=normalize_policy_path_fn,
        parse_path_list_fn=parse_path_list_fn,
        dedupe_compact_items_fn=dedupe_compact_items_fn,
        paths_outside_policy_fn=paths_outside_policy_fn,
    )
    out_of_scope_files = list(review_state["out_of_scope_files"] or [])
    modified_files = list(review_state["modified_files"] or [])
    if out_of_scope_files:
        result = tasks_execution_runtime.build_staged_apply_blocked_result(
            current=current,
            artifact=artifact,
            out_of_scope_files=out_of_scope_files,
            task_id=task_id,
            utc_now_iso_fn=utc_now_iso,
            trim_error_fn=trim_error_fn,
        )
        storage.write_result_snapshot(
            task_id,
            tasks_flow_runtime.updated_review_payload(
                review_payload,
                final_apply_pending=False,
                final_apply_state="blocked",
                out_of_scope_files=out_of_scope_files,
                review_commands=result.artifact["review_commands"],
            ),
            suffix="teammate_review",
        )
        return persist_updated_result_fn(storage, result)
    tasks_flow_runtime.apply_staged_changes(
        review_payload=review_payload,
        live_cwd=live_cwd,
        stage_cwd=stage_cwd,
        normalize_policy_path_fn=normalize_policy_path_fn,
    )
    applied_at = utc_now_iso()
    result = tasks_execution_runtime.build_staged_apply_completed_result(
        current=current,
        artifact=artifact,
        modified_files=modified_files,
        applied_at=applied_at,
    )
    storage.write_result_snapshot(
        task_id,
        tasks_flow_runtime.updated_review_payload(
            review_payload,
            final_apply_pending=False,
            final_apply_state="applied",
            review_commands=[],
            applied_files=modified_files,
            final_apply_decided_at=applied_at,
        ),
        suffix="teammate_review",
    )
    return persist_updated_result_fn(storage, result)
