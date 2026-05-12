from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import file_query_match_runtime
from cli.agent_cli.tools_core.file_query_path_runtime import (
    normalize_query_text,
    resolve_workspace_path,
)


def file_list(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str],
    limit: int,
    list_dir_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    root = workspace_root.resolve()
    current_root = cwd_root.resolve()
    try:
        target = resolve_workspace_path(
            root,
            path,
            default_root=current_root,
            file_tool_error_cls=FileNotFoundError,
        )
    except Exception as exc:
        return ToolEvent(
            name="file_list",
            ok=False,
            summary="file list failed",
            payload={
                "ok": False,
                "workspace_root": str(root),
                "error": str(exc),
                "path": str(path or "").strip() or ".",
                "compatibility_alias": "list_dir",
            },
        )
    list_dir_event = list_dir_fn(
        workspace_root=root,
        cwd_root=current_root,
        dir_path=str(target.resolve()),
        offset=1,
        limit=max(1, int(limit or 50)),
        depth=8,
    )
    if not list_dir_event.ok:
        payload = dict(list_dir_event.payload or {})
        payload["compatibility_alias"] = "list_dir"
        return ToolEvent(
            name="file_list",
            ok=False,
            summary="file list failed",
            payload=payload,
        )
    entries = [dict(item) for item in list_dir_event.payload.get("entries") or [] if isinstance(item, dict)]
    files: List[Dict[str, Any]] = []
    for item in entries:
        if str(item.get("kind") or "") != "file":
            continue
        rel_path = str(item.get("path") or "").strip()
        if not rel_path:
            continue
        size = 0
        try:
            item_path = (target / rel_path).resolve()
            if item_path.is_file():
                size = int(item_path.stat().st_size)
        except OSError:
            size = 0
        files.append({"path": rel_path, "size": size})
    payload = {
        "ok": True,
        "workspace_root": str(root),
        "path": str(list_dir_event.payload.get("dir_path") or "."),
        "count": len(files),
        "files": files,
        "engine": "compat:list_dir",
        "compatibility_alias": "list_dir",
    }
    return ToolEvent(name="file_list", ok=True, summary=f"files={len(files)}", payload=payload)


def file_search(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: Optional[str],
    limit: int,
    grep_files_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    root = workspace_root.resolve()
    current_root = cwd_root.resolve()
    normalized_query = normalize_query_text(str(query or ""))
    if not normalized_query:
        return ToolEvent(
            name="file_search",
            ok=False,
            summary="file search failed",
            payload={
                "ok": False,
                "workspace_root": str(root),
                "error": "query is required",
                "query": "",
            },
        )
    grep_event = grep_files_fn(
        workspace_root=root,
        cwd_root=current_root,
        pattern=normalized_query,
        include=None,
        path=path,
        limit=limit,
    )
    if not grep_event.ok:
        payload = dict(grep_event.payload or {})
        payload["compatibility_alias"] = "grep_files"
        payload["query"] = normalized_query
        return ToolEvent(name="file_search", ok=False, summary="file search failed", payload=payload)
    payload = file_query_match_runtime.build_file_search_payload(
        root=root,
        grep_payload=dict(grep_event.payload or {}),
        normalized_query=normalized_query,
    )
    return ToolEvent(
        name="file_search",
        ok=bool(payload["matches"]),
        summary=(f"file matches={len(payload['matches'])}" if payload["matches"] else "No matches found."),
        payload=payload,
    )
