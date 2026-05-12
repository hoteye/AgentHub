from __future__ import annotations

import json
from typing import Any


def append_lifecycle_lines_impl(
    lines: list[str],
    *,
    lifecycle: dict[str, Any],
    payload: dict[str, Any],
    artifact: dict[str, Any],
) -> None:
    lifecycle_queue_source = str(lifecycle.get("queue_source_of_truth") or artifact.get("queue_source_of_truth") or "").strip()
    if lifecycle_queue_source:
        lines.append(f"lifecycle_queue_source_of_truth={lifecycle_queue_source}")
    lifecycle_queue_provider = str(lifecycle.get("queue_provider") or artifact.get("queue_provider") or "").strip()
    if lifecycle_queue_provider:
        lines.append(f"lifecycle_queue_provider={lifecycle_queue_provider}")
    lifecycle_queue_state = str(lifecycle.get("queue_state") or payload.get("queue_state") or "").strip()
    if lifecycle_queue_state:
        lines.append(f"lifecycle_queue_state={lifecycle_queue_state}")
    lifecycle_dispatch_id = lifecycle.get("dispatch_id")
    if lifecycle_dispatch_id in (None, "", 0):
        lifecycle_dispatch_id = payload.get("dispatch_id")
    if lifecycle_dispatch_id not in (None, "", 0):
        lines.append(f"lifecycle_dispatch_id={lifecycle_dispatch_id}")
    lifecycle_last_event = str(lifecycle.get("last_event") or artifact.get("lifecycle_last_event") or "").strip()
    if lifecycle_last_event:
        lines.append(f"lifecycle_last_event={lifecycle_last_event}")
    lifecycle_cleanup_count = lifecycle.get("cleanup_count")
    if lifecycle_cleanup_count in (None, ""):
        lifecycle_cleanup_count = artifact.get("lifecycle_cleanup_count")
    if lifecycle_cleanup_count not in (None, ""):
        lines.append(f"lifecycle_cleanup_count={lifecycle_cleanup_count}")
    lifecycle_restore_count = lifecycle.get("restore_count")
    if lifecycle_restore_count in (None, ""):
        lifecycle_restore_count = artifact.get("lifecycle_restore_count")
    if lifecycle_restore_count not in (None, ""):
        lines.append(f"lifecycle_restore_count={lifecycle_restore_count}")
    lifecycle_stale_requeue_count = lifecycle.get("stale_requeue_count")
    if lifecycle_stale_requeue_count in (None, ""):
        lifecycle_stale_requeue_count = artifact.get("stale_requeue_count")
    if lifecycle_stale_requeue_count not in (None, ""):
        lines.append(f"lifecycle_stale_requeue_count={lifecycle_stale_requeue_count}")


def append_bootstrap_lines_impl(lines: list[str], *, bootstrap: dict[str, Any]) -> None:
    for key in ("cwd_exists", "is_dir", "git_root_detected", "git_dir_present"):
        if key in bootstrap:
            lines.append(f"{key}={'true' if bootstrap.get(key) else 'false'}")
    git_root = str(bootstrap.get("git_root") or "").strip()
    if git_root:
        lines.append(f"git_root={git_root}")
    repo_state = bootstrap.get("repo_state")
    if repo_state is not None:
        lines.append(f"repo_state={json.dumps(repo_state, ensure_ascii=False)}")
    for key in ("dependency_files", "bootstrap_warnings"):
        value = bootstrap.get(key)
        if value is not None:
            lines.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    bootstrap_error_category = str(bootstrap.get("bootstrap_error_category") or "").strip()
    if bootstrap_error_category:
        lines.append(f"bootstrap_error_category={bootstrap_error_category}")
