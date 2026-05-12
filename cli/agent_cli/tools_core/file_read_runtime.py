from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.file_read_runtime_helpers import (
    build_file_read_payload,
    build_read_file_payload,
)


def file_read(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    root = workspace_root.resolve()
    current_root = cwd_root.resolve()
    try:
        target = resolve_workspace_path_fn(root, path, default_root=current_root)
        if not target.exists():
            raise file_tool_error_cls(f"path not found: {path}")
        if not target.is_file():
            raise file_tool_error_cls(f"path is not a file: {path}")
        payload = build_file_read_payload(
            root=current_root,
            target=target,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
            relative_text_fn=relative_text_fn,
            file_tool_error_cls=file_tool_error_cls,
        )
        payload["workspace_root"] = str(root)
        payload["requested_path"] = str(path or "").strip()
        return ToolEvent(name="file_read", ok=True, summary="file loaded", payload=payload)
    except Exception as exc:
        return ToolEvent(
            name="file_read",
            ok=False,
            summary="file read failed",
            payload={
                "ok": False,
                "workspace_root": str(root),
                "error": str(exc),
                "path": str(path or "").strip(),
                "requested_path": str(path or "").strip(),
            },
        )


def read_file(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    root = workspace_root.resolve()
    current_root = cwd_root.resolve()
    requested_file_path = str(file_path or "").strip()
    mode_text = str(mode or "slice").strip().lower() or "slice"
    if mode_text not in {"slice", "indentation"}:
        error_text = "mode must be slice or indentation"
        return ToolEvent(
            name="read_file",
            ok=False,
            summary="read file failed",
            payload={
                "ok": False,
                "workspace_root": str(root),
                "error": error_text,
                "file_path": requested_file_path,
                "mode": mode,
                "indentation": dict(indentation or {}) or None,
                "function_call_output": error_text,
                "function_call_output_model_visible": True,
            },
        )
    try:
        if not Path(requested_file_path).is_absolute():
            raise file_tool_error_cls("file_path must be an absolute path")
        target = resolve_workspace_path_fn(root, requested_file_path, default_root=current_root)
        if not target.exists():
            raise file_tool_error_cls(f"path not found: {requested_file_path}")
        if not target.is_file():
            raise file_tool_error_cls(f"path is not a file: {requested_file_path}")
        payload = build_read_file_payload(
            root=current_root,
            target=target,
            offset=offset,
            limit=limit,
            mode_text=mode_text,
            indentation=indentation,
            relative_text_fn=relative_text_fn,
            file_tool_error_cls=file_tool_error_cls,
        )
        resolved_target = str(target.resolve())
        payload["file_path"] = resolved_target
        payload["path"] = resolved_target
        payload["workspace_root"] = str(root)
        payload["requested_path"] = requested_file_path
        return ToolEvent(name="read_file", ok=True, summary="file loaded", payload=payload)
    except Exception as exc:
        error_text = str(exc)
        return ToolEvent(
            name="read_file",
            ok=False,
            summary="read file failed",
            payload={
                "ok": False,
                "workspace_root": str(root),
                "error": error_text,
                "file_path": requested_file_path,
                "requested_path": requested_file_path,
                "mode": mode_text,
                "indentation": dict(indentation or {}) or None,
                "function_call_output": error_text,
                "function_call_output_model_visible": True,
            },
        )


def file_read_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    file_read_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    event = file_read_fn(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )
    arguments: Dict[str, Any] = {"path": str(path or "").strip()}
    if offset is not None:
        arguments["offset"] = int(offset)
    if limit is not None:
        arguments["limit"] = int(limit)
    if max_chars is not None:
        arguments["max_chars"] = int(max_chars)
    return structured_result_from_event_fn(
        assistant_text="Read workspace file.",
        event=event,
        tool_name="file_read",
        arguments=arguments,
    )


def read_file_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
    read_file_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    event = read_file_fn(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )
    arguments: Dict[str, Any] = {"file_path": str(file_path or "").strip()}
    if offset is not None:
        arguments["offset"] = int(offset)
    if limit is not None:
        arguments["limit"] = int(limit)
    if mode is not None:
        arguments["mode"] = str(mode)
    if indentation:
        arguments["indentation"] = dict(indentation)
    return structured_result_from_event_fn(
        assistant_text="Read workspace file.",
        event=event,
        tool_name="read_file",
        arguments=arguments,
    )
