from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, TypeVar

from cli.agent_cli import workspace_context_assembly_runtime as workspace_context_assembly_runtime_helpers
from cli.agent_cli import workspace_context_facade_runtime as workspace_context_facade_runtime_helpers
from cli.agent_cli import workspace_context_private_runtime as workspace_context_private_runtime_helpers
from cli.agent_cli import workspace_context_projection_runtime as workspace_context_projection_runtime_helpers

WorkspaceSkillT = TypeVar("WorkspaceSkillT")


def parse_skill_file(
    path: Path,
    *,
    safe_resolve_fn: Callable[[str | Path], Path],
    skill_factory: Callable[..., WorkspaceSkillT],
) -> Optional[WorkspaceSkillT]:
    return workspace_context_private_runtime_helpers.parse_skill_file(
        path,
        safe_resolve_fn=safe_resolve_fn,
        skill_factory=skill_factory,
    )


def repo_skill_roots(
    cwd: Path,
    project_root: Path,
    markers: List[str],
    *,
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], List[Path]],
    safe_resolve_fn: Callable[[str | Path], Path],
    agents_dirname: str,
    legacy_repo_config_dirname: str,
    skills_dirname: str,
) -> List[Path]:
    return workspace_context_private_runtime_helpers.repo_skill_roots(
        cwd,
        project_root,
        markers,
        dirs_between_project_root_and_cwd=dirs_between_project_root_and_cwd_fn,
        safe_resolve_fn=safe_resolve_fn,
        agents_dirname=agents_dirname,
        legacy_repo_config_dirname=legacy_repo_config_dirname,
        skills_dirname=skills_dirname,
    )


def discover_repo_skills(
    cwd: str | Path,
    *,
    safe_resolve_fn: Callable[[str | Path], Path],
    project_root_markers_fn: Callable[[str | Path], List[str]],
    find_project_root_fn: Callable[[str | Path, Iterable[str]], Path],
    repo_skill_roots_fn: Callable[[Path, Path, List[str]], List[Path]],
    discover_skills_from_roots_fn: Callable[[Sequence[str | Path]], List[WorkspaceSkillT]],
) -> List[WorkspaceSkillT]:
    return list(
        workspace_context_assembly_runtime_helpers.discover_repo_skills(
            cwd,
            safe_resolve=safe_resolve_fn,
            project_root_markers_fn=project_root_markers_fn,
            find_project_root_fn=find_project_root_fn,
            repo_skill_roots_fn=repo_skill_roots_fn,
            discover_skills_from_roots_fn=discover_skills_from_roots_fn,
        )
    )


def discover_skills_from_roots(
    skill_roots: Sequence[str | Path],
    *,
    safe_resolve_fn: Callable[[str | Path], Path],
    skill_filename: str,
    max_skill_scan_depth: int,
    parse_skill_file_fn: Callable[[Path], Optional[WorkspaceSkillT]],
    include_hidden: bool = False,
) -> List[WorkspaceSkillT]:
    return list(
        workspace_context_assembly_runtime_helpers.discover_skills_from_roots(
            skill_roots,
            safe_resolve=safe_resolve_fn,
            skill_filename=skill_filename,
            max_skill_scan_depth=max_skill_scan_depth,
            parse_skill_file=parse_skill_file_fn,
            include_hidden=include_hidden,
        )
    )


def discover_workspace_skills(
    cwd: str | Path,
    *,
    discover_repo_skills_fn: Callable[[str | Path], List[WorkspaceSkillT]],
    discover_skills_from_roots_fn: Callable[[Sequence[str | Path]], List[WorkspaceSkillT]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> List[WorkspaceSkillT]:
    return list(
        workspace_context_assembly_runtime_helpers.discover_workspace_skills(
            cwd,
            discover_repo_skills_fn=discover_repo_skills_fn,
            discover_skills_from_roots_fn=discover_skills_from_roots_fn,
            extra_skill_roots=extra_skill_roots,
        )
    )


def render_skills_section(skills: List[WorkspaceSkillT], *, skill_usage_rules: str) -> Optional[str]:
    return workspace_context_projection_runtime_helpers.render_skills_section(skills, skill_usage_rules=skill_usage_rules)


def explicitly_mentioned_skills(text: str, skills: List[WorkspaceSkillT]) -> List[WorkspaceSkillT]:
    return list(workspace_context_projection_runtime_helpers.explicitly_mentioned_skills(text, skills))


def render_explicit_skill_injections(
    text: str,
    skills: List[WorkspaceSkillT] | str | Path | None,
    *,
    render_explicit_skill_injections_runtime_fn: Callable[..., Optional[str]],
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], List[WorkspaceSkillT]],
    explicitly_mentioned_skills_fn: Callable[[str, List[WorkspaceSkillT]], List[WorkspaceSkillT]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Optional[str]:
    return workspace_context_facade_runtime_helpers.render_explicit_skill_injections(
        text,
        skills,
        render_explicit_skill_injections_runtime_fn=render_explicit_skill_injections_runtime_fn,
        discover_workspace_skills_fn=discover_workspace_skills_fn,
        explicitly_mentioned_skills_fn=explicitly_mentioned_skills_fn,
        extra_skill_roots=extra_skill_roots,
    )
