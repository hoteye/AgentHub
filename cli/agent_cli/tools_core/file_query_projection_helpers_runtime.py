from __future__ import annotations

from pathlib import Path

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core.file_query_path_runtime import relative_text
from cli.agent_cli.tools_core.file_query_pure_helpers_runtime import ListDirPage


def _list_dir_payload_path(*, target: Path, cwd_root: Path) -> str:
    return relative_text(target, cwd_root) if target != cwd_root else "."


def _list_dir_rendered_lines(*, page: ListDirPage, limit: int) -> list[str]:
    lines = [
        f"E{page.start_index + index + 1}: [{item['kind']}] {item['path']}"
        for index, item in enumerate(page.selected_entries)
    ]
    if page.truncated:
        lines.append(f"More than {limit} entries found")
    return lines


def _codex_list_dir_entry_line(entry: dict[str, str]) -> str:
    normalized_path = str(entry.get("path") or "").replace("\\", "/").strip("/")
    name = normalized_path.rsplit("/", 1)[-1] if normalized_path else ""
    depth = normalized_path.count("/") if normalized_path else 0
    kind = str(entry.get("kind") or "").strip().lower()
    suffix = ""
    if kind == "dir":
        suffix = "/"
    elif kind == "symlink":
        suffix = "@"
    elif kind not in {"file", ""}:
        suffix = "?"
    return f"{' ' * (depth * 2)}{name}{suffix}"


def _list_dir_function_call_output(*, target: Path, page: ListDirPage, limit: int) -> str:
    lines = [f"Absolute path: {target.resolve()}"]
    lines.extend(_codex_list_dir_entry_line(entry) for entry in page.selected_entries)
    if page.truncated:
        lines.append(f"More than {limit} entries found")
    return "\n".join(lines)


def build_list_dir_success_event(
    *,
    root: Path,
    cwd_root: Path,
    target: Path,
    offset: int,
    limit: int,
    depth: int,
    page: ListDirPage,
) -> ToolEvent:
    rendered_lines = _list_dir_rendered_lines(page=page, limit=limit)
    payload = {
        "ok": True,
        "workspace_root": str(root),
        "dir_path": _list_dir_payload_path(target=target, cwd_root=cwd_root),
        "offset": offset,
        "limit": limit,
        "depth": depth,
        "count": page.total_count,
        "returned_count": len(page.selected_entries),
        "entries": [
            {
                "index": page.start_index + index + 1,
                "kind": item["kind"],
                "path": item["path"],
            }
            for index, item in enumerate(page.selected_entries)
        ],
        "truncated": page.truncated,
        "text": "\n".join(rendered_lines),
        "function_call_output": _list_dir_function_call_output(
            target=target,
            page=page,
            limit=limit,
        ),
        "function_call_output_model_visible": True,
    }
    return ToolEvent(
        name="list_dir",
        ok=True,
        summary=f"entries={len(page.selected_entries)}",
        payload=payload,
    )


def build_list_dir_error_event(
    *,
    root: Path,
    dir_path: str | None,
    offset: int,
    limit: int,
    depth: int,
    default_offset: int,
    default_limit: int,
    default_depth: int,
    error: Exception,
) -> ToolEvent:
    error_text = str(error)
    return ToolEvent(
        name="list_dir",
        ok=False,
        summary="list dir failed",
        payload={
            "ok": False,
            "workspace_root": str(root),
            "error": error_text,
            "dir_path": str(dir_path or "").strip() or ".",
            "offset": int(offset or default_offset),
            "limit": int(limit or default_limit),
            "depth": int(depth or default_depth),
            "function_call_output": error_text,
            "function_call_output_model_visible": True,
        },
    )


__all__ = [
    "build_list_dir_error_event",
    "build_list_dir_success_event",
]
