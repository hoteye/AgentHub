from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional

from cli.agent_cli.tools_core import file_query_match_runtime

from .file_query_path_runtime import query_arg_for_target, relative_text


def rg_grep_files(
    *,
    workspace_root: Path,
    target: Path,
    pattern: str,
    include: str | None,
    limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
) -> Optional[List[str]]:
    if not which_fn("rg"):
        return None
    command: List[str] = ["rg", "--sortr=modified", "--regexp", str(pattern), "--no-messages"]
    if output_mode == "files_with_matches":
        command.append("--files-with-matches")
    elif output_mode == "count":
        command.append("--count")
    # content mode: no extra flag
    if case_insensitive:
        command.append("--ignore-case")
    if file_type:
        command.extend(["--type", str(file_type)])
    if output_mode == "content":
        if line_numbers:
            command.append("--line-number")
        if multiline:
            command.append("--multiline")
        if context is not None:
            command.extend(["--context", str(int(context))])
        elif after_context is not None or before_context is not None:
            if after_context is not None:
                command.extend(["--after-context", str(int(after_context))])
            if before_context is not None:
                command.extend(["--before-context", str(int(before_context))])
    include_text = str(include or "").strip()
    if include_text:
        command.extend(["--glob", include_text])
    command.extend(["--", query_arg_for_target(target, workspace_root)])
    result = run_fn(
        command,
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        stderr_text = str(result.stderr or "").strip() or "unknown rg failure"
        raise file_tool_error_cls(f"rg failed: {stderr_text}")
    if output_mode == "files_with_matches":
        paths = file_query_match_runtime.collect_rg_paths(
            output=result.stdout,
            workspace_root=workspace_root,
            limit=limit + offset,
        )
        return paths[offset:offset + limit] if offset else paths
    lines = [line for line in result.stdout.splitlines()]
    if offset:
        lines = lines[offset:]
    return lines[:limit] if limit else lines


def python_grep_files(
    *,
    workspace_root: Path,
    target: Path,
    pattern: str,
    include: str | None,
    limit: int,
    file_tool_error_cls: type[Exception],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    line_numbers: bool = False,
    after_context: Optional[int] = None,
    before_context: Optional[int] = None,
    context: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
) -> List[str]:
    return file_query_match_runtime.python_grep_files(
        workspace_root=workspace_root,
        target=target,
        pattern=pattern,
        include=include,
        limit=limit,
        relative_text_fn=relative_text,
        file_tool_error_cls=file_tool_error_cls,
        output_mode=output_mode,
        case_insensitive=case_insensitive,
        file_type=file_type,
        line_numbers=line_numbers,
        after_context=after_context,
        before_context=before_context,
        context=context,
        offset=offset,
        multiline=multiline,
    )
