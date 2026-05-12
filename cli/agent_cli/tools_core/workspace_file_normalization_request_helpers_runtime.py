from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.tools_core.workspace_file_pure_helpers_runtime import (
    Payload,
    build_workspace_file_payload,
)


def normalize_apply_patch_request(
    *,
    patch_text: str,
    workspace_root: Path,
) -> Payload:
    return build_workspace_file_payload(
        patch_text=patch_text,
        workspace_root=workspace_root,
    )


def normalize_glob_files_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        pattern=pattern,
        path=path,
        limit=limit,
    )


def normalize_grep_files_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = 100,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        pattern=pattern,
        include=include,
        path=path,
        limit=limit,
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


def normalize_list_dir_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def normalize_read_file_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )


def normalize_file_list_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str | None = None,
    limit: int = 50,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        limit=limit,
    )


def normalize_file_search_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: str | None = None,
    limit: int = 20,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        query=query,
        path=path,
        limit=limit,
    )


def normalize_file_read_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> Payload:
    return build_workspace_file_payload(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )


__all__ = [
    "normalize_apply_patch_request",
    "normalize_file_list_request",
    "normalize_file_read_request",
    "normalize_file_search_request",
    "normalize_glob_files_request",
    "normalize_grep_files_request",
    "normalize_list_dir_request",
    "normalize_read_file_request",
]
