from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core.file_query_path_runtime import relative_text


def _normalized_result_lines(items: list[Any]) -> list[str]:
    return [str(item).strip() for item in items if str(item).strip()]


def _payload_path(*, target: Path, cwd_root: Path) -> str:
    return relative_text(target, cwd_root) if target != cwd_root else "."


def build_glob_success_event(
    *,
    root: Path,
    cwd_root: Path,
    target: Path,
    requested_path: str,
    requested_pattern: str,
    search_pattern: str,
    max_items: int,
    result: dict[str, Any],
    engine: str,
) -> ToolEvent:
    paths = _normalized_result_lines(list(result.get("paths") or []))
    text = "\n".join(paths) if paths else "No files found."
    result_success = bool(paths)
    payload = {
        "ok": result_success,
        "result_success": result_success,
        "workspace_root": str(root),
        "path": _payload_path(target=target, cwd_root=cwd_root),
        "requested_path": requested_path,
        "pattern": requested_pattern,
        "search_pattern": search_pattern,
        "limit": max_items,
        "count": len(paths),
        "file_count": len(paths),
        "paths": paths,
        "filenames": paths,
        "truncated": bool(result.get("truncated")),
        "text": text,
        "engine": engine,
    }
    return ToolEvent(
        name="glob_files",
        ok=result_success,
        summary=(f"files={len(paths)}" if paths else "No files found."),
        payload=payload,
    )


def build_glob_error_event(
    *,
    root: Path,
    requested_path: str,
    requested_pattern: str,
    error: Exception,
) -> ToolEvent:
    return ToolEvent(
        name="glob_files",
        ok=False,
        summary="glob files failed",
        payload={
            "ok": False,
            "workspace_root": str(root),
            "error": str(error),
            "pattern": requested_pattern,
            "path": requested_path,
            "requested_path": requested_path,
        },
    )


def build_grep_success_event(
    *,
    root: Path,
    cwd_root: Path,
    target: Path,
    requested_path: str,
    normalized_pattern: str,
    normalized_include: str | None,
    max_items: int,
    lines: list[str],
    engine: str,
    output_mode: str = "files_with_matches",
) -> ToolEvent:
    paths = list(lines)
    text = "\n".join(paths) if paths else "No matches found."
    result_success = bool(paths)
    payload = {
        "ok": result_success,
        "result_success": result_success,
        "workspace_root": str(root),
        "path": _payload_path(target=target, cwd_root=cwd_root),
        "requested_path": requested_path,
        "pattern": normalized_pattern,
        "include": normalized_include,
        "limit": max_items,
        "count": len(paths),
        "paths": paths,
        "text": text,
        "engine": engine,
    }
    if output_mode == "files_with_matches" and paths:
        absolute_lines: list[str] = []
        for item in paths:
            candidate = Path(str(item))
            if not candidate.is_absolute():
                candidate = (root / candidate).resolve()
            absolute_lines.append(str(candidate))
        payload["function_call_output"] = "\n".join(absolute_lines)
        payload["function_call_output_model_visible"] = True
    return ToolEvent(
        name="grep_files",
        ok=result_success,
        summary=(f"paths={len(paths)}" if paths else "No matches found."),
        payload=payload,
    )


def build_grep_error_event(
    *,
    root: Path,
    requested_path: str,
    pattern: str,
    include: str | None,
    error: Exception,
) -> ToolEvent:
    return ToolEvent(
        name="grep_files",
        ok=False,
        summary="grep files failed",
        payload={
            "ok": False,
            "workspace_root": str(root),
            "error": str(error),
            "pattern": pattern,
            "path": requested_path,
            "requested_path": requested_path,
            "include": include,
        },
    )
