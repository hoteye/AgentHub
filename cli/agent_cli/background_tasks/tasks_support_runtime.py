from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from .models import BackgroundTaskStatus
from . import tasks_support_diagnostics_runtime
from . import tasks_support_workspace_runtime


def normalize_argv(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if isinstance(value, str):
        return shlex.split(value, posix=True)
    return []


def normalize_smoke_kind(payload: dict[str, Any], *, smoke_kind_scripts: dict[str, Path]) -> str:
    raw = str(payload.get("kind") or payload.get("suite") or "").strip().lower()
    if raw in smoke_kind_scripts:
        return raw
    return "multi_llm"


def dedupe_compact_items(values: list[str], *, limit: int | None = None) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if limit is not None and len(items) >= limit:
            break
    return items


def relative_task_path(base: Path, candidate: Any) -> str:
    text = str(candidate or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return path.as_posix()


def tool_payload_path_candidates(payload: dict[str, Any], *, include_path: bool = False) -> list[str]:
    candidates: list[str] = []
    for key in ("changed_file", "touched_file"):
        value = str(payload.get(key) or "").strip()
        if value:
            candidates.append(value)
    for key in ("changed_files", "touched_files"):
        value = payload.get(key)
        if isinstance(value, (list, tuple)):
            candidates.extend(str(item or "").strip() for item in value if str(item or "").strip())
    if include_path:
        value = str(payload.get("path") or "").strip()
        if value:
            candidates.append(value)
    return candidates


def teammate_modified_files(response_payload: dict[str, Any], *, cwd: Path) -> list[str]:
    files: list[str] = []
    for item in list(response_payload.get("tool_events") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if name == "apply_patch":
            changes = payload.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    relative_path = relative_task_path(cwd, change.get("path"))
                    if relative_path:
                        files.append(relative_path)
            files.extend(relative_task_path(cwd, candidate) for candidate in tool_payload_path_candidates(payload, include_path=True))
            continue
        files.extend(relative_task_path(cwd, candidate) for candidate in tool_payload_path_candidates(payload))
    return dedupe_compact_items(files, limit=32)


def teammate_commands(response_payload: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for item in teammate_command_policy_summary(response_payload):
        command = str(item.get("command") or "").strip()
        effective_command = str(item.get("effective_command") or "").strip()
        if command:
            commands.append(command)
        if effective_command and effective_command != command:
            commands.append(effective_command)
        if bool(item.get("policy_denied")):
            denied_target = command or effective_command
            marker = f"policy_denied: {denied_target}" if denied_target else "policy_denied"
            commands.append(marker)
    return dedupe_compact_items(commands, limit=12)


def teammate_command_policy_summary(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in list(response_payload.get("tool_events") or []):
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        command = str(payload.get("command") or "").strip()
        effective_command = str(payload.get("effective_command") or "").strip()
        status = str(payload.get("status") or "").strip()
        command_policy = payload.get("command_policy")
        policy_mapping = dict(command_policy) if isinstance(command_policy, dict) else {}
        policy_allowed = policy_mapping.get("allowed")
        policy_denied = status.lower() == "policy_denied" or policy_allowed is False
        error_code = str(payload.get("error_code") or policy_mapping.get("error_code") or "").strip()
        if not (command or effective_command or status or policy_denied):
            continue
        key = (command, effective_command, status, error_code)
        if key in seen:
            continue
        seen.add(key)
        summary.append(
            {
                "command": command,
                "effective_command": effective_command,
                "status": status,
                "policy_denied": policy_denied,
                "error_code": error_code,
                "command_policy": policy_mapping,
            }
        )
    return summary


def teammate_test_commands(commands: list[str]) -> list[str]:
    test_markers = (
        "pytest",
        "python -m pytest",
        "unittest",
        "python -m unittest",
        "nose",
        "nosetests",
        "tox",
        "nox",
        "npm test",
        "pnpm test",
        "yarn test",
        "vitest",
        "jest",
        "go test",
        "cargo test",
    )
    return [command for command in commands if any(marker in command for marker in test_markers)]


def parse_path_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_items = [str(item or "").strip() for item in value]
    else:
        raw_items = [segment.strip() for segment in str(value or "").split(",")]
    return dedupe_compact_items([item for item in raw_items if item], limit=32)


def task_timeout_seconds(payload: dict[str, Any]) -> float | None:
    raw = payload.get("timeout_seconds")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def timeout_error_text(task_label: str, timeout_seconds: float | None) -> str:
    if timeout_seconds is None:
        return f"{task_label} task exceeded timeout"
    return f"{task_label} task exceeded timeout_seconds={timeout_seconds:g}"


def background_terminal_state(
    *,
    status: BackgroundTaskStatus,
    cancelled: bool = False,
    timed_out: bool = False,
) -> str:
    if cancelled or status == BackgroundTaskStatus.CANCELLED:
        return "cancelled"
    if timed_out:
        return "timed_out"
    if status == BackgroundTaskStatus.COMPLETED:
        return "completed"
    if status == BackgroundTaskStatus.FAILED:
        return "failed"
    return ""


def mapping_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def response_status_mapping(value: Any) -> dict[str, Any]:
    payload = mapping_dict(value)
    return {str(key): payload[key] for key in payload}


def route_report_from_status(status: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(status, dict) or not status:
        return {}
    routes = {
        str(key).removeprefix("route_"): str(value or "").strip()
        for key, value in status.items()
        if str(key).startswith("route_") and str(value or "").strip()
    }
    report: dict[str, Any] = {}
    for key in ("provider_name", "provider_model", "provider_label", "timing_summary"):
        value = str(status.get(key) or "").strip()
        if value:
            report[key] = value
    if routes:
        report["routes"] = routes
    return report


def find_git_root(path: Path) -> Path | None:
    return tasks_support_diagnostics_runtime.find_git_root(path)


def capture_command_output(command: list[str], *, cwd: Path) -> str | None:
    return tasks_support_diagnostics_runtime.capture_command_output(command, cwd=cwd)


def git_repo_state(git_root: Path, *, warnings: list[str]) -> dict[str, Any] | None:
    return tasks_support_diagnostics_runtime.git_repo_state(git_root, warnings=warnings)


def collect_bootstrap_diagnostics(cwd: Path, *, bootstrap_dependency_files: tuple[str, ...]) -> dict[str, Any]:
    return tasks_support_diagnostics_runtime.collect_bootstrap_diagnostics(
        cwd,
        bootstrap_dependency_files=bootstrap_dependency_files,
        relative_task_path_fn=relative_task_path,
        dedupe_compact_items_fn=lambda values: dedupe_compact_items(values),
    )


def bootstrap_diagnostic_artifact_fields(diagnostics: dict[str, Any]) -> dict[str, Any]:
    return tasks_support_diagnostics_runtime.bootstrap_diagnostic_artifact_fields(diagnostics)


def bootstrap_failure_error(diagnostics: dict[str, Any]) -> str:
    return tasks_support_diagnostics_runtime.bootstrap_failure_error(diagnostics)


def normalize_policy_path(base: Path, candidate: Any) -> str:
    return tasks_support_diagnostics_runtime.normalize_policy_path(base, candidate)


def path_matches_rule(path_text: str, rule: str) -> bool:
    return tasks_support_diagnostics_runtime.path_matches_rule(path_text, rule)


def paths_outside_policy(
    paths: list[str],
    *,
    allowed_paths: list[str],
    blocked_paths: list[str],
) -> list[str]:
    return tasks_support_diagnostics_runtime.paths_outside_policy(
        paths,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        dedupe_compact_items_fn=lambda values: dedupe_compact_items(values),
    )


def stage_workspace_ignore(source_root: Path, storage: Any):
    return tasks_support_workspace_runtime.stage_workspace_ignore(source_root, storage)


def prepare_stage_workspace(task_id: str, *, source_root: Path, storage: Any) -> Path:
    return tasks_support_workspace_runtime.prepare_stage_workspace(
        task_id,
        source_root=source_root,
        storage=storage,
    )


def workspace_file_index(root: Path) -> dict[str, Path]:
    return tasks_support_workspace_runtime.workspace_file_index(root)


def diff_preview(
    *,
    relative_path: str,
    before_path: Path | None,
    after_path: Path | None,
) -> tuple[bool, str]:
    return tasks_support_workspace_runtime.diff_preview(
        relative_path=relative_path,
        before_path=before_path,
        after_path=after_path,
    )


def collect_workspace_changes(source_root: Path, stage_root: Path) -> list[dict[str, Any]]:
    return tasks_support_workspace_runtime.collect_workspace_changes(source_root, stage_root)


def teammate_review_commands(task_id: str, *, blocked: bool) -> list[str]:
    commands: list[str] = []
    if not blocked:
        commands.append(f"/background_task_apply {task_id}")
    commands.append(f"/background_task_reject {task_id}")
    return commands


def benchmark_success_summary(report_path: Path) -> str:
    return tasks_support_diagnostics_runtime.benchmark_success_summary(report_path)


def smoke_success_summary(kind: str, report_path: Path) -> str:
    return tasks_support_diagnostics_runtime.smoke_success_summary(kind, report_path)


def trim_error(text: str, *, max_chars: int = 280) -> str:
    return tasks_support_diagnostics_runtime.trim_error(text, max_chars=max_chars)


def decode_json_text(text: str) -> dict[str, Any] | None:
    return tasks_support_diagnostics_runtime.decode_json_text(text)


def load_review_payload(path_text: Any) -> dict[str, Any]:
    return tasks_support_workspace_runtime.load_review_payload(path_text)
