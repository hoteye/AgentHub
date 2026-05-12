from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli.models import ToolEvent


DELEGATED_PATH_KEYS = {
    "path",
    "paths",
    "file",
    "files",
    "filepath",
    "file_path",
    "dir",
    "dirs",
    "dir_path",
    "directory",
    "directories",
    "cwd",
    "workdir",
    "workspace_root",
    "repo_root",
    "root",
    "root_dir",
    "root_path",
    "target",
    "target_path",
    "target_file",
    "source_path",
    "source_paths",
    "source_file",
    "input_path",
    "input_paths",
    "input_file",
    "output_path",
    "output_paths",
    "output_file",
    "changed_file",
    "changed_files",
    "touched_file",
    "touched_files",
    "markdown_path",
    "moved_from",
}


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def workspace_root(runtime: Any) -> Path:
    raw_cwd = str(getattr(runtime, "cwd", "") or ".").strip() or "."
    try:
        return Path(raw_cwd).expanduser().resolve(strict=False)
    except Exception:
        return Path(raw_cwd)


def looks_like_windows_abs_path(text: str) -> bool:
    return len(text) > 2 and text[1] == ":" and text[2] in {"/", "\\"}


def normalize_delegated_path(runtime: Any, candidate: Any) -> str:
    text = str(candidate or "").strip()
    if not text or "://" in text or "\n" in text:
        return ""
    if looks_like_windows_abs_path(text):
        return text
    root = workspace_root(runtime)
    try:
        raw_path = Path(text).expanduser()
        if raw_path.is_absolute():
            return str(raw_path.resolve(strict=False))
        return str((root / raw_path).resolve(strict=False))
    except Exception:
        return ""


def parse_structured_result(text: str) -> Any | None:
    candidate = str(text or "").strip()
    if not candidate or candidate[0] not in {"{", "["}:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def delegated_result_artifact(*, status: str, assistant_text: str, error: str) -> Dict[str, Any]:
    normalized_status = str(status or "").strip().lower() or "queued"
    normalized_text = str(assistant_text or "").strip()
    normalized_error = str(error or "").strip()
    structured = parse_structured_result(normalized_text) if normalized_text else None
    if normalized_status in {"queued", "starting", "running", "closing"}:
        return {"kind": "pending"}
    if normalized_status == "closed":
        return {"kind": "empty"}
    if normalized_status == "failed":
        artifact: Dict[str, Any] = {
            "kind": "failure",
            "error": normalized_error or "delegated agent failed",
        }
        if normalized_text:
            artifact["text"] = normalized_text
        return artifact
    if structured is not None:
        return {
            "kind": "structured",
            "format": "json",
            "structured": structured,
        }
    if normalized_text:
        return {
            "kind": "text",
            "text": normalized_text,
        }
    if normalized_error:
        return {
            "kind": "failure",
            "error": normalized_error,
        }
    return {"kind": "empty"}


def delegated_result_confidence(*, status: str, artifact: Dict[str, Any], touched_scope: List[str]) -> str:
    normalized_status = str(status or "").strip().lower() or "queued"
    if normalized_status in {"queued", "starting", "running", "closing"}:
        return "pending"
    if normalized_status == "closed":
        return "low"
    artifact_kind = str(artifact.get("kind") or "").strip().lower()
    if artifact_kind == "structured":
        return "high"
    if artifact_kind == "text":
        return "high" if touched_scope else "medium"
    if artifact_kind in {"failure", "empty"}:
        return "low"
    return "medium"


def collect_delegated_paths(runtime: Any, value: Any, depth: int = 0, *, path_hint: bool = False) -> List[str]:
    if depth > 4:
        return []
    collected: List[str] = []

    def _append(candidate: Any) -> None:
        normalized = normalize_delegated_path(runtime, candidate)
        if normalized and normalized not in collected:
            collected.append(normalized)

    if isinstance(value, ToolEvent):
        return collect_delegated_paths(runtime, value.to_dict(), depth=depth + 1, path_hint=path_hint)
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key or "").strip().lower()
            nested_path_hint = path_hint or normalized_key in DELEGATED_PATH_KEYS
            if nested_path_hint and isinstance(nested, (list, tuple, set)):
                for item in list(nested):
                    _append(item)
            elif nested_path_hint and not isinstance(nested, dict):
                _append(nested)
            for item in collect_delegated_paths(runtime, nested, depth=depth + 1, path_hint=nested_path_hint):
                if item not in collected:
                    collected.append(item)
        return collected[:8]
    if isinstance(value, (list, tuple, set)):
        for nested in list(value):
            for item in collect_delegated_paths(runtime, nested, depth=depth + 1, path_hint=path_hint):
                if item not in collected:
                    collected.append(item)
        return collected[:8]
    if path_hint:
        _append(value)
    return collected[:8]


def delegated_result_contract_payload(
    runtime: Any,
    *,
    goal: str,
    status: str,
    assistant_text: str,
    error: str,
    adopted: bool,
    touched_sources: List[Any],
    role: str = "",
    delegation_mode: str = "",
    wait_required: bool | None = None,
    delegated_completion_policy_fn: Any,
    delegated_completion_state_fn: Any,
) -> Dict[str, Any]:
    normalized_status = str(status or "").strip().lower() or "queued"
    completion_policy = delegated_completion_policy_fn(
        role=role,
        delegation_mode=delegation_mode,
        wait_required=wait_required,
    )
    completion_state = delegated_completion_state_fn(
        status=normalized_status,
        adopted=adopted,
        completion_policy=completion_policy,
    )
    touched_scope = collect_delegated_paths(runtime, touched_sources)
    artifact = delegated_result_artifact(
        status=normalized_status,
        assistant_text=assistant_text,
        error=error,
    )
    artifact_kind = str(artifact.get("kind") or "").strip().lower()
    if normalized_status == "completed":
        summary = preview_text(assistant_text or "delegated task completed", max_chars=160)
        confidence = delegated_result_confidence(
            status=normalized_status,
            artifact=artifact,
            touched_scope=touched_scope,
        )
        if artifact_kind == "empty":
            next_action = "inspect_or_retry_empty_result" if not adopted else "already_adopted"
        elif completion_state == "adopted":
            next_action = "already_adopted"
        elif completion_state == "ready_to_adopt":
            next_action = "review_or_adopt_teammate_result"
        else:
            next_action = "wait_agent_to_adopt"
    elif normalized_status == "failed":
        summary = preview_text(error or "delegated agent failed", max_chars=160)
        confidence = delegated_result_confidence(
            status=normalized_status,
            artifact=artifact,
            touched_scope=touched_scope,
        )
        next_action = "failure_observed" if adopted else "inspect_error_or_retry"
    elif normalized_status == "closed":
        summary = preview_text(
            error or "delegated task closed before producing a result",
            max_chars=160,
        )
        confidence = delegated_result_confidence(
            status=normalized_status,
            artifact=artifact,
            touched_scope=touched_scope,
        )
        next_action = "already_adopted" if adopted else "resume_agent_to_continue"
    elif normalized_status in {"running", "starting", "closing"}:
        summary = f"delegated task {normalized_status}"
        confidence = delegated_result_confidence(
            status=normalized_status,
            artifact=artifact,
            touched_scope=touched_scope,
        )
        next_action = "continue_main_thread_or_wait"
    else:
        summary = "delegated task queued"
        confidence = delegated_result_confidence(
            status=normalized_status,
            artifact=artifact,
            touched_scope=touched_scope,
        )
        next_action = "continue_main_thread_or_wait"
    return {
        "goal": str(goal or "").strip(),
        "status": normalized_status,
        "summary": summary,
        "artifact": artifact,
        "confidence": confidence,
        "touched_scope": touched_scope,
        "completion_policy": completion_policy,
        "completion_state": completion_state,
        "next_action": next_action,
    }
