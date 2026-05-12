from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from cli.agent_cli import workspace_context_config_runtime as workspace_context_config_runtime_service
from cli.agent_cli import workspace_context_prompt_runtime as workspace_context_prompt_runtime_service
from cli.agent_cli import workspace_context_reference_runtime as workspace_context_reference_runtime_service


def workspace_config_candidates(
    cwd: Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_local_data_dir_candidates: Sequence[str],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    return workspace_context_config_runtime_service.workspace_config_candidates(
        cwd,
        safe_resolve=safe_resolve,
        project_local_data_dir_candidates=project_local_data_dir_candidates,
        home_config_paths=list(home_config_paths or (agent_cli_home / "config.toml", legacy_compat_home / "config.toml")),
    )


def existing_home_config_paths(
    *,
    safe_resolve: Callable[[Path], Path],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    return workspace_context_config_runtime_service.existing_home_config_paths(
        safe_resolve=safe_resolve,
        home_config_paths=list(home_config_paths or (agent_cli_home / "config.toml", legacy_compat_home / "config.toml")),
    )


def merged_home_workspace_config(
    *,
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    existing_home_config_paths_fn: Callable[..., List[Path]],
    read_toml_fn: Callable[[Path], Dict[str, Any]],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    return workspace_context_config_runtime_service.merged_home_workspace_config(
        merge_nested_mappings=merge_nested_mappings,
        existing_home_config_paths_fn=existing_home_config_paths_fn,
        read_toml_fn=read_toml_fn,
        home_config_paths=list(home_config_paths or (agent_cli_home / "config.toml", legacy_compat_home / "config.toml")),
    )


def merged_workspace_config(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    workspace_config_candidates_fn: Callable[..., List[Path]],
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    read_toml_fn: Callable[[Path], Dict[str, Any]],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    return workspace_context_config_runtime_service.merged_workspace_config(
        cwd,
        safe_resolve=safe_resolve,
        workspace_config_candidates_fn=workspace_config_candidates_fn,
        merge_nested_mappings=merge_nested_mappings,
        read_toml_fn=read_toml_fn,
        home_config_paths=list(home_config_paths or (agent_cli_home / "config.toml", legacy_compat_home / "config.toml")),
    )


def workspace_trust_level(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    merged_home_workspace_config_fn: Callable[..., Dict[str, Any]],
    home_config_paths: Optional[Sequence[Path]] = None,
) -> str:
    resolved_cwd = safe_resolve(Path(cwd))
    home_config = merged_home_workspace_config_fn(home_config_paths=home_config_paths)
    projects = home_config.get("projects")
    if not isinstance(projects, dict):
        return "trusted"
    best_match: tuple[int, str] | None = None
    for root_text, payload in projects.items():
        try:
            candidate_root = safe_resolve(Path(str(root_text)))
        except OSError:
            continue
        if candidate_root != resolved_cwd and candidate_root not in resolved_cwd.parents:
            continue
        if isinstance(payload, dict):
            level = str(payload.get("trust_level") or payload.get("trustLevel") or "").strip().lower()
        else:
            level = str(payload or "").strip().lower()
        normalized = level if level in {"trusted", "untrusted", "unknown"} else "unknown"
        score = len(str(candidate_root))
        if best_match is None or score > best_match[0]:
            best_match = (score, normalized)
    if best_match is None:
        return "unknown"
    return best_match[1]


def find_project_root(cwd: str | Path, markers: Iterable[str], *, safe_resolve: Callable[[Path], Path]) -> Path:
    resolved_cwd = safe_resolve(Path(cwd))
    marker_list = [str(item or "").strip() for item in markers if str(item or "").strip()]
    if not marker_list:
        return resolved_cwd
    for ancestor in [resolved_cwd, *resolved_cwd.parents]:
        for marker in marker_list:
            if (ancestor / marker).exists():
                return ancestor
    return resolved_cwd


def dirs_between_project_root_and_cwd(
    cwd: str | Path,
    project_root: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
) -> List[Path]:
    resolved_cwd = safe_resolve(Path(cwd))
    resolved_root = safe_resolve(Path(project_root))
    trail = [resolved_cwd, *resolved_cwd.parents]
    ordered = list(reversed(trail))
    if resolved_root not in ordered:
        return [resolved_cwd]
    return ordered[ordered.index(resolved_root) :]


def discover_project_doc_paths(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_root_markers_fn: Callable[[str | Path], List[str]],
    find_project_root_fn: Callable[[str | Path, Iterable[str]], Path],
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], List[Path]],
    project_doc_fallback_filenames_fn: Callable[[str | Path], List[str]],
    local_project_doc_filename: str,
    default_project_doc_filename: str,
) -> List[Path]:
    return workspace_context_config_runtime_service.discover_project_doc_paths(
        cwd,
        safe_resolve=safe_resolve,
        project_root_markers_fn=project_root_markers_fn,
        find_project_root_fn=find_project_root_fn,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd_fn,
        project_doc_fallback_filenames_fn=project_doc_fallback_filenames_fn,
        local_project_doc_filename=local_project_doc_filename,
        default_project_doc_filename=default_project_doc_filename,
    )


def discover_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    safe_resolve: Callable[[Path], Path],
    workspace_trust_level_fn: Callable[[str | Path], str],
    project_root_markers_fn: Callable[[str | Path], List[str]],
    find_project_root_fn: Callable[[str | Path, Iterable[str]], Path],
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], List[Path]],
    project_local_data_dir_candidates: Sequence[str],
) -> List[Path]:
    return workspace_context_config_runtime_service.discover_project_local_paths(
        filename,
        cwd=cwd,
        safe_resolve=safe_resolve,
        workspace_trust_level_fn=workspace_trust_level_fn,
        project_root_markers_fn=project_root_markers_fn,
        find_project_root_fn=find_project_root_fn,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd_fn,
        project_local_data_dir_candidates=project_local_data_dir_candidates,
    )


def merge_project_file_configs(
    *,
    cwd: str | Path,
    filename: str,
    discover_project_local_paths_fn: Callable[..., List[Path]],
    safe_resolve: Callable[[Path], Path],
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    reader_fn: Callable[[Path], Dict[str, Any]],
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Tuple[Dict[str, Any], List[Path]]:
    return workspace_context_config_runtime_service.merge_project_file_configs(
        cwd=cwd,
        filename=filename,
        discover_project_local_paths_fn=discover_project_local_paths_fn,
        safe_resolve=safe_resolve,
        merge_nested_mappings=merge_nested_mappings,
        reader_fn=reader_fn,
        home_config_paths=home_config_paths,
    )


def discover_repo_skills(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_root_markers_fn: Callable[[str | Path], List[str]],
    find_project_root_fn: Callable[[str | Path, Iterable[str]], Path],
    repo_skill_roots_fn: Callable[[Path, Path, List[str]], List[Path]],
    discover_skills_from_roots_fn: Callable[[Sequence[str | Path]], List[Any]],
) -> List[Any]:
    return list(
        workspace_context_prompt_runtime_service.discover_repo_skills(
            cwd,
            safe_resolve=safe_resolve,
            project_root_markers=project_root_markers_fn,
            find_project_root=find_project_root_fn,
            repo_skill_roots=repo_skill_roots_fn,
            discover_skills_from_roots=discover_skills_from_roots_fn,
        )
    )


def discover_skills_from_roots(
    skill_roots: Sequence[str | Path],
    *,
    safe_resolve: Callable[[Path], Path],
    skill_filename: str,
    max_skill_scan_depth: int,
    parse_skill_file: Callable[[Path], Any],
    include_hidden: bool = False,
) -> List[Any]:
    return list(
        workspace_context_prompt_runtime_service.discover_skills_from_roots(
            skill_roots,
            safe_resolve=safe_resolve,
            skill_filename=skill_filename,
            max_skill_scan_depth=max_skill_scan_depth,
            parse_skill_file=parse_skill_file,
            include_hidden=include_hidden,
        )
    )


def discover_workspace_skills(
    cwd: str | Path,
    *,
    discover_repo_skills_fn: Callable[[str | Path], List[Any]],
    discover_skills_from_roots_fn: Callable[[Sequence[str | Path]], List[Any]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> List[Any]:
    return list(
        workspace_context_prompt_runtime_service.discover_workspace_skills(
            cwd,
            discover_repo_skills=discover_repo_skills_fn,
            discover_skills_from_roots=discover_skills_from_roots_fn,
            extra_skill_roots=extra_skill_roots,
        )
    )


def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    read_project_docs_fn: Callable[..., Optional[str]],
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], List[Any]],
    render_skills_section_fn: Callable[[List[Any]], Optional[str]],
    context_factory: Callable[..., Any],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Any:
    return workspace_context_prompt_runtime_service.build_workspace_prompt_context(
        cwd,
        safe_resolve=safe_resolve,
        read_project_docs=read_project_docs_fn,
        discover_workspace_skills=discover_workspace_skills_fn,
        render_skills_section=render_skills_section_fn,
        context_factory=context_factory,
        extra_skill_roots=extra_skill_roots,
    )


def build_workspace_reference_snapshot(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
    max_chars: int,
    build_workspace_prompt_context_fn: Callable[..., Any],
    safe_resolve: Callable[[Path], Path],
    text_digest: Callable[[str], str],
    discover_project_doc_paths_fn: Callable[..., List[Path]],
    path_signature: Callable[[Path], Dict[str, Any]],
    workspace_trust_level_fn: Callable[[str | Path], str],
) -> Dict[str, Any]:
    return workspace_context_reference_runtime_service.build_workspace_reference_snapshot(
        cwd,
        extra_skill_roots=extra_skill_roots,
        max_chars=max_chars,
        build_workspace_prompt_context=build_workspace_prompt_context_fn,
        safe_resolve=safe_resolve,
        text_digest=text_digest,
        discover_project_doc_paths=discover_project_doc_paths_fn,
        path_signature=path_signature,
        workspace_trust_level=workspace_trust_level_fn,
    )


def render_explicit_skill_injections(
    text: str,
    skills: List[Any] | str | Path | None,
    *,
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], List[Any]],
    explicitly_mentioned_skills_fn: Callable[[str, List[Any]], List[Any]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Optional[str]:
    return workspace_context_prompt_runtime_service.render_explicit_skill_injections(
        text,
        skills,
        discover_workspace_skills=discover_workspace_skills_fn,
        explicitly_mentioned_skills=explicitly_mentioned_skills_fn,
        extra_skill_roots=extra_skill_roots,
    )
