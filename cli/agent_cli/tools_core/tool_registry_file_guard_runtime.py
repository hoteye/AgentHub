from __future__ import annotations

import os
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import apply_patch_runtime


def normalize_workspace_file_path(registry: Any, raw_path: str) -> str:
    workspace_root_getter = getattr(registry, "file_workspace_root", None)
    workspace_root = (
        workspace_root_getter() if callable(workspace_root_getter) else registry.workspace_root()
    )
    candidate = os.path.normpath(str(raw_path or "").strip())
    if not candidate:
        return ""
    if os.path.isabs(candidate):
        return candidate
    return os.path.normpath(os.path.join(str(workspace_root), candidate))


def claude_structured_edit_arguments(request: Any) -> dict[str, Any]:
    if str(request.kind or "") == "write":
        return {
            "file_path": str(request.file_path or ""),
            "content": str(request.content or ""),
        }
    arguments = {
        "file_path": str(request.file_path or ""),
        "old_string": str(request.old_string or ""),
        "new_string": str(request.new_string or ""),
    }
    if bool(request.replace_all):
        arguments["replace_all"] = True
    return arguments


def claude_structured_edit_guard_failure_event(
    registry: Any,
    *,
    request: Any,
    error: str,
    guard_failure: str = "",
) -> ToolEvent:
    request_kind = "structured_write" if str(request.kind or "") == "write" else "structured_edit"
    function_call_name = str(
        request.source_tool_name or ("Write" if request_kind == "structured_write" else "Edit")
    )
    payload = {
        "ok": False,
        "error": str(error or "Edit failed."),
        "request_kind": request_kind,
        "function_call_name": function_call_name,
        "function_call_arguments": claude_structured_edit_arguments(request),
        "source_tool_name": function_call_name,
        "guard_profile": str(request.guard_profile or ""),
    }
    if guard_failure:
        payload["guard_failure"] = guard_failure
    return registry._event(
        "apply_patch",
        False,
        "apply_patch failed",
        payload,
    )


def claude_structured_edit_guard_event(registry: Any, patch_text: str) -> ToolEvent | None:
    request = apply_patch_runtime.parse_structured_request(patch_text)
    if request is None:
        return None
    guard_profile = str(request.guard_profile or "").strip()
    if guard_profile not in {"claude_write", "claude_edit"}:
        return None
    normalized_path = normalize_workspace_file_path(registry, request.file_path)
    if not normalized_path:
        return None
    if not os.path.exists(normalized_path):
        if guard_profile == "claude_write":
            return None
        return claude_structured_edit_guard_failure_event(
            registry,
            request=request,
            error=f"Edit requires an existing file: {request.file_path}",
            guard_failure="missing_target",
        )
    if os.path.isdir(normalized_path):
        return claude_structured_edit_guard_failure_event(
            registry,
            request=request,
            error=f"cannot edit directory without reading it first: {request.file_path}",
        )
    read_state = dict(getattr(registry, "_file_read_state", {}) or {}).get(normalized_path)
    if not isinstance(read_state, dict):
        action = "Write" if guard_profile == "claude_write" else "Edit"
        return claude_structured_edit_guard_failure_event(
            registry,
            request=request,
            error=f"{action} requires reading the current file first for safety: {request.file_path}",
            guard_failure="read_before_write_required",
        )
    try:
        stat_result = os.stat(normalized_path)
    except OSError as exc:
        return claude_structured_edit_guard_failure_event(
            registry,
            request=request,
            error=f"{'Write' if guard_profile == 'claude_write' else 'Edit'} safety check failed: {exc}",
            guard_failure="stat_failed",
        )
    current_state = {
        "mtime_ns": int(getattr(stat_result, "st_mtime_ns", 0) or 0),
        "size": int(getattr(stat_result, "st_size", 0) or 0),
    }
    if current_state != {
        "mtime_ns": int(read_state.get("mtime_ns") or 0),
        "size": int(read_state.get("size") or 0),
    }:
        action = "Write" if guard_profile == "claude_write" else "Edit"
        suffix = "overwriting" if guard_profile == "claude_write" else "editing"
        return claude_structured_edit_guard_failure_event(
            registry,
            request=request,
            error=f"{action} target changed since it was read. Re-read before {suffix}: {request.file_path}",
            guard_failure="stale_after_read",
        )
    return None


def remember_full_file_read(
    registry: Any,
    *,
    event: ToolEvent,
    requested_path: str,
    offset: int | None,
    limit: int | None,
    max_chars: int | None = None,
) -> None:
    if not bool(getattr(event, "ok", False)):
        return
    payload = dict(getattr(event, "payload", {}) or {})
    if bool(payload.get("truncated")):
        return
    if max_chars is not None:
        return
    total_line_count = payload.get("line_count")
    returned_line_count = payload.get("returned_line_count")
    if offset not in (None, 1):
        return
    if (
        total_line_count is not None
        and returned_line_count is not None
        and int(returned_line_count) < int(total_line_count)
    ):
        return
    if limit is not None and total_line_count is not None and int(limit) < int(total_line_count):
        return
    relative_path = str(
        payload.get("file_path") or payload.get("path") or requested_path or ""
    ).strip()
    if not relative_path:
        return
    normalized_path = normalize_workspace_file_path(registry, relative_path)
    if not normalized_path or not os.path.exists(normalized_path):
        return
    try:
        stat_result = os.stat(normalized_path)
    except OSError:
        return
    registry._file_read_state[normalized_path] = {
        "mtime_ns": int(getattr(stat_result, "st_mtime_ns", 0) or 0),
        "size": int(getattr(stat_result, "st_size", 0) or 0),
    }
