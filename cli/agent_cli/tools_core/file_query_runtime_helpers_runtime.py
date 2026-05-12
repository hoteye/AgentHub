from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core.file_query_compat_runtime import (
    file_list as _file_list,
    file_search as _file_search,
)
from cli.agent_cli.tools_core.file_query_glob_runtime import (
    python_glob_files as python_glob_matches,
    rg_glob_files,
)
from cli.agent_cli.tools_core.file_query_grep_runtime import (
    python_grep_files,
    rg_grep_files,
)
from cli.agent_cli.tools_core.file_query_list_runtime import collect_list_dir_entries
from cli.agent_cli.tools_core.file_query_normalization_helpers_runtime import (
    prepare_list_dir_request,
)
from cli.agent_cli.tools_core.file_query_path_runtime import relative_text
from cli.agent_cli.tools_core.file_query_projection_helpers_runtime import (
    build_list_dir_error_event,
    build_list_dir_success_event,
)
from cli.agent_cli.tools_core.file_query_pure_helpers_runtime import (
    paginate_list_dir_entries,
    run_query_backend_fallback,
)
from cli.agent_cli.tools_core.file_query_request_runtime import (
    normalize_requested_path,
    prepare_glob_request,
    prepare_grep_request,
)
from cli.agent_cli.tools_core.file_query_result_runtime import (
    build_glob_error_event,
    build_glob_success_event,
    build_grep_error_event,
    build_grep_success_event,
)


def _resolved_roots(workspace_root: Path, cwd_root: Path) -> tuple[Path, Path]:
    return workspace_root.resolve(), cwd_root.resolve()


def glob_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: Optional[str],
    limit: int,
    glob_default_limit: int,
    glob_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    root, current_root = _resolved_roots(workspace_root, cwd_root)
    requested_path = normalize_requested_path(path)
    requested_pattern = str(pattern or "").strip()
    try:
        request = prepare_glob_request(
            workspace_root=root,
            cwd_root=current_root,
            pattern=pattern,
            path=path,
            limit=limit,
            default_limit=glob_default_limit,
            maximum_limit=glob_max_limit,
            file_tool_error_cls=file_tool_error_cls,
        )
        backend_result = run_query_backend_fallback(
            rg_call=lambda: rg_glob_files(
                workspace_root=current_root,
                target=request.target,
                pattern=request.search_pattern,
                limit=request.max_items,
                which_fn=which_fn,
                run_fn=run_fn,
                relative_text_fn=relative_text,
                file_tool_error_cls=file_tool_error_cls,
            ),
            python_call=lambda: python_glob_matches(
                workspace_root=current_root,
                target=request.target,
                pattern=request.search_pattern,
                limit=request.max_items,
                relative_text_fn=relative_text,
            ),
        )
        return build_glob_success_event(
            root=root,
            cwd_root=current_root,
            target=request.target,
            requested_path=request.requested_path,
            requested_pattern=request.requested_pattern,
            search_pattern=request.search_pattern,
            max_items=request.max_items,
            result=backend_result.result,
            engine=backend_result.engine,
        )
    except Exception as exc:
        return build_glob_error_event(
            root=root,
            requested_path=requested_path,
            requested_pattern=requested_pattern,
            error=exc,
        )


def grep_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: Optional[str],
    path: Optional[str],
    limit: int,
    grep_default_limit: int,
    grep_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
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
) -> ToolEvent:
    root, current_root = _resolved_roots(workspace_root, cwd_root)
    requested_path = normalize_requested_path(path)
    try:
        request = prepare_grep_request(
            workspace_root=root,
            cwd_root=current_root,
            pattern=pattern,
            include=include,
            path=path,
            limit=limit,
            default_limit=grep_default_limit,
            maximum_limit=grep_max_limit,
            file_tool_error_cls=file_tool_error_cls,
        )
        backend_result = run_query_backend_fallback(
            rg_call=lambda: rg_grep_files(
                workspace_root=current_root,
                target=request.target,
                pattern=request.normalized_pattern,
                include=request.normalized_include,
                limit=request.max_items,
                which_fn=which_fn,
                run_fn=run_fn,
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
            ),
            python_call=lambda: python_grep_files(
                workspace_root=current_root,
                target=request.target,
                pattern=request.normalized_pattern,
                include=request.normalized_include,
                limit=request.max_items,
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
            ),
        )
        return build_grep_success_event(
            root=root,
            cwd_root=current_root,
            target=request.target,
            requested_path=request.requested_path,
            normalized_pattern=request.normalized_pattern,
            normalized_include=request.normalized_include,
            max_items=request.max_items,
            lines=backend_result.result,
            engine=backend_result.engine,
            output_mode=output_mode,
        )
    except Exception as exc:
        return build_grep_error_event(
            root=root,
            requested_path=requested_path,
            pattern=str(pattern or "").strip(),
            include=str(include or "").strip() or None,
            error=exc,
        )


def list_dir(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: Optional[str],
    offset: int,
    limit: int,
    depth: int,
    list_default_offset: int,
    list_default_limit: int,
    list_default_depth: int,
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    root, current_root = _resolved_roots(workspace_root, cwd_root)
    try:
        request = prepare_list_dir_request(
            workspace_root=root,
            cwd_root=current_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
            default_offset=list_default_offset,
            default_limit=list_default_limit,
            default_depth=list_default_depth,
            file_tool_error_cls=file_tool_error_cls,
        )
        all_entries = collect_list_dir_entries(
            request.target,
            depth=request.depth,
            file_tool_error_cls=file_tool_error_cls,
        )
        page = paginate_list_dir_entries(
            all_entries=all_entries,
            offset=request.offset,
            limit=request.limit,
            file_tool_error_cls=file_tool_error_cls,
        )
        return build_list_dir_success_event(
            root=root,
            cwd_root=current_root,
            target=request.target,
            offset=request.offset,
            limit=request.limit,
            depth=request.depth,
            page=page,
        )
    except Exception as exc:
        return build_list_dir_error_event(
            root=root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
            default_offset=list_default_offset,
            default_limit=list_default_limit,
            default_depth=list_default_depth,
            error=exc,
        )


def file_list(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str],
    limit: int,
    list_dir_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return _file_list(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        limit=limit,
        list_dir_fn=list_dir_fn,
    )


def file_search(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: Optional[str],
    limit: int,
    grep_files_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return _file_search(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        query=query,
        path=path,
        limit=limit,
        grep_files_fn=grep_files_fn,
    )
