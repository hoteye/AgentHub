from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def project_doc_fallback_filenames_from_config(
    *,
    configured: Sequence[str],
    default_project_doc_filename: str,
    local_project_doc_filename: str,
    legacy_local_project_doc_filenames: Sequence[str],
    legacy_project_doc_filenames: Sequence[str],
) -> List[str]:
    fallback_names: List[str] = []
    seen: set[str] = {default_project_doc_filename, local_project_doc_filename}
    for name in [*configured, *legacy_local_project_doc_filenames, *legacy_project_doc_filenames]:
        normalized = str(name or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        fallback_names.append(normalized)
    return fallback_names


def discover_project_doc_paths(
    cwd: str | Path,
    *,
    discover_project_doc_paths_runtime_fn: Any,
    safe_resolve: Any,
    project_root_markers_fn: Any,
    find_project_root_fn: Any,
    dirs_between_project_root_and_cwd_fn: Any,
    project_doc_fallback_filenames_fn: Any,
    local_project_doc_filename: str,
    default_project_doc_filename: str,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    return discover_project_doc_paths_runtime_fn(
        cwd,
        safe_resolve=safe_resolve,
        project_root_markers_fn=lambda value: project_root_markers_fn(value, home_config_paths=home_config_paths),
        find_project_root_fn=find_project_root_fn,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd_fn,
        project_doc_fallback_filenames_fn=lambda value: project_doc_fallback_filenames_fn(
            value,
            home_config_paths=home_config_paths,
        ),
        local_project_doc_filename=local_project_doc_filename,
        default_project_doc_filename=default_project_doc_filename,
    )


def read_project_docs(
    cwd: str | Path,
    *,
    read_project_docs_runtime_fn: Any,
    discover_project_doc_paths_fn: Any,
    max_total_bytes: int,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Optional[str]:
    return read_project_docs_runtime_fn(
        cwd,
        max_total_bytes=max_total_bytes,
        discover_project_doc_paths_fn=lambda value: discover_project_doc_paths_fn(
            value,
            home_config_paths=home_config_paths,
        ),
    )


def discover_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    discover_project_local_paths_runtime_fn: Any,
    safe_resolve: Any,
    workspace_trust_level_fn: Any,
    project_root_markers_fn: Any,
    find_project_root_fn: Any,
    dirs_between_project_root_and_cwd_fn: Any,
    project_local_data_dir_candidates: Sequence[str],
    home_config_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    return discover_project_local_paths_runtime_fn(
        filename,
        cwd=cwd,
        safe_resolve=safe_resolve,
        workspace_trust_level_fn=lambda value: workspace_trust_level_fn(value, home_config_paths=home_config_paths),
        project_root_markers_fn=lambda value: project_root_markers_fn(value, home_config_paths=home_config_paths),
        find_project_root_fn=find_project_root_fn,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd_fn,
        project_local_data_dir_candidates=project_local_data_dir_candidates,
    )


def read_merged_project_file_configs(
    *,
    cwd: str | Path,
    filename: str,
    merge_project_file_configs_runtime_fn: Any,
    discover_project_local_paths_fn: Any,
    safe_resolve: Any,
    merge_nested_mappings: Any,
    reader_fn: Any,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> tuple[Dict[str, Any], List[Path]]:
    return merge_project_file_configs_runtime_fn(
        cwd=cwd,
        filename=filename,
        discover_project_local_paths_fn=lambda selected_filename, *, cwd, home_config_paths=None: discover_project_local_paths_fn(
            selected_filename,
            cwd=cwd,
            home_config_paths=home_config_paths,
        ),
        safe_resolve=safe_resolve,
        merge_nested_mappings=merge_nested_mappings,
        reader_fn=reader_fn,
        home_config_paths=home_config_paths,
    )


def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    build_workspace_prompt_context_runtime_fn: Any,
    safe_resolve: Any,
    read_project_docs_fn: Any,
    discover_workspace_skills_fn: Any,
    render_skills_section_fn: Any,
    context_factory: Any,
    empty_context_factory: Any,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Any:
    return build_workspace_prompt_context_runtime_fn(
        cwd,
        safe_resolve=safe_resolve,
        read_project_docs_fn=read_project_docs_fn,
        discover_workspace_skills_fn=lambda resolved_cwd, roots: discover_workspace_skills_fn(
            resolved_cwd,
            extra_skill_roots=roots,
        ),
        render_skills_section_fn=render_skills_section_fn,
        context_factory=context_factory,
        empty_context_factory=empty_context_factory,
        extra_skill_roots=extra_skill_roots,
    )


def render_explicit_skill_injections(
    text: str,
    skills: List[Any] | str | Path | None,
    *,
    render_explicit_skill_injections_runtime_fn: Any,
    discover_workspace_skills_fn: Any,
    explicitly_mentioned_skills_fn: Any,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Optional[str]:
    return render_explicit_skill_injections_runtime_fn(
        text,
        skills,
        discover_workspace_skills_fn=lambda resolved_cwd, roots: discover_workspace_skills_fn(
            resolved_cwd,
            extra_skill_roots=roots,
        ),
        explicitly_mentioned_skills_fn=explicitly_mentioned_skills_fn,
        extra_skill_roots=extra_skill_roots,
    )
