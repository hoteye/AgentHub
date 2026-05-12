from __future__ import annotations

from pathlib import Path
from typing import Optional

from cli.agent_cli.tools_core import file_query_match_runtime


def resolve_workspace_path(
    workspace_root: Path,
    raw_path: Optional[str],
    *,
    default_root: Path | None = None,
    file_tool_error_cls: type[Exception],
) -> Path:
    resolved_root = workspace_root.resolve()
    base_root = Path(default_root).resolve() if default_root is not None else resolved_root
    try:
        base_root.relative_to(resolved_root)
    except ValueError:
        base_root = resolved_root
    candidate_text = str(raw_path or "").strip()
    if not candidate_text:
        return base_root
    candidate = Path(candidate_text)
    if not candidate.is_absolute():
        candidate = base_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise file_tool_error_cls(f"path escapes workspace root: {raw_path}") from exc
    return resolved


def relative_text(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def normalize_rel_path(path_text: str) -> str:
    return file_query_match_runtime.normalize_rel_path(path_text)


def normalize_query_text(query: str) -> str:
    return file_query_match_runtime.normalize_query_text(query)


def query_arg_for_target(target: Path, workspace_root: Path) -> str:
    return file_query_match_runtime.query_arg_for_target(
        target,
        workspace_root,
        relative_text_fn=relative_text,
    )


def clamp_positive(
    value: int,
    *,
    default: int,
    maximum: int | None = None,
    file_tool_error_cls: type[Exception],
) -> int:
    resolved = int(value or default)
    if resolved <= 0:
        raise file_tool_error_cls("value must be greater than zero")
    if maximum is not None:
        return min(resolved, int(maximum))
    return resolved
