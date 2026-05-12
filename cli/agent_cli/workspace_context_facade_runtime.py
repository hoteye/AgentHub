from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence


SKILL_USAGE_RULES = """- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""


def workspace_config_candidates(
    cwd: Path,
    *,
    safe_resolve: Callable[[str | Path], Path],
    project_local_data_dir_candidates: Sequence[str],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]],
    workspace_config_candidates_runtime_fn: Callable[..., list[Path]],
) -> list[Path]:
    return workspace_config_candidates_runtime_fn(
        cwd,
        safe_resolve=safe_resolve,
        project_local_data_dir_candidates=project_local_data_dir_candidates,
        agent_cli_home=agent_cli_home,
        legacy_compat_home=legacy_compat_home,
        home_config_paths=home_config_paths,
    )


def existing_home_config_paths(
    *,
    safe_resolve: Callable[[str | Path], Path],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]],
    existing_home_config_paths_runtime_fn: Callable[..., list[Path]],
) -> list[Path]:
    return existing_home_config_paths_runtime_fn(
        safe_resolve=safe_resolve,
        agent_cli_home=agent_cli_home,
        legacy_compat_home=legacy_compat_home,
        home_config_paths=home_config_paths,
    )


def merged_home_workspace_config(
    *,
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    existing_home_config_paths_fn: Callable[[], list[Path]],
    read_toml_fn: Callable[[Path], Dict[str, Any]],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]],
    merged_home_workspace_config_runtime_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    return merged_home_workspace_config_runtime_fn(
        merge_nested_mappings=merge_nested_mappings,
        existing_home_config_paths_fn=existing_home_config_paths_fn,
        read_toml_fn=read_toml_fn,
        agent_cli_home=agent_cli_home,
        legacy_compat_home=legacy_compat_home,
        home_config_paths=home_config_paths,
    )


def merged_workspace_config(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[str | Path], Path],
    workspace_config_candidates_fn: Callable[[Path], list[Path]],
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    read_toml_fn: Callable[[Path], Dict[str, Any]],
    agent_cli_home: Path,
    legacy_compat_home: Path,
    home_config_paths: Optional[Sequence[Path]],
    merged_workspace_config_runtime_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    return merged_workspace_config_runtime_fn(
        cwd,
        safe_resolve=safe_resolve,
        workspace_config_candidates_fn=workspace_config_candidates_fn,
        merge_nested_mappings=merge_nested_mappings,
        read_toml_fn=read_toml_fn,
        agent_cli_home=agent_cli_home,
        legacy_compat_home=legacy_compat_home,
        home_config_paths=home_config_paths,
    )


def discover_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    safe_resolve: Callable[[str | Path], Path],
    workspace_trust_level_fn: Callable[[str | Path], str],
    project_root_markers_fn: Callable[[str | Path], list[str]],
    find_project_root_fn: Callable[[str | Path, Sequence[str]], Path],
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], list[Path]],
    project_local_data_dir_candidates: Sequence[str],
    discover_project_local_paths_runtime_fn: Callable[..., list[Path]],
) -> list[Path]:
    return discover_project_local_paths_runtime_fn(
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
    discover_project_local_paths_fn: Callable[..., list[Path]],
    safe_resolve: Callable[[str | Path], Path],
    merge_nested_mappings: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    reader_fn: Callable[[Path], Dict[str, Any]],
    home_config_paths: Optional[Sequence[Path]],
    merge_project_file_configs_runtime_fn: Callable[..., tuple[Dict[str, Any], list[Path]]],
) -> tuple[Dict[str, Any], list[Path]]:
    return merge_project_file_configs_runtime_fn(
        cwd=cwd,
        filename=filename,
        discover_project_local_paths_fn=discover_project_local_paths_fn,
        safe_resolve=safe_resolve,
        merge_nested_mappings=merge_nested_mappings,
        reader_fn=reader_fn,
        home_config_paths=home_config_paths,
    )


def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[str | Path], Path],
    read_project_docs_fn: Callable[..., Optional[str]],
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], list[Any]],
    render_skills_section_fn: Callable[[list[Any]], Optional[str]],
    context_factory: Any,
    empty_context_factory: Any,
    extra_skill_roots: Optional[Sequence[str | Path]],
    build_workspace_prompt_context_runtime_fn: Callable[..., Any],
) -> Any:
    return build_workspace_prompt_context_runtime_fn(
        cwd,
        safe_resolve=safe_resolve,
        read_project_docs_fn=read_project_docs_fn,
        discover_workspace_skills_fn=lambda resolved_cwd, roots: discover_workspace_skills_fn(
            resolved_cwd,
            roots,
        ),
        render_skills_section_fn=render_skills_section_fn,
        context_factory=context_factory,
        empty_context_factory=empty_context_factory,
        extra_skill_roots=extra_skill_roots,
    )


def render_workspace_prompt_addendum(
    cwd: str | Path | None,
    *,
    build_workspace_prompt_context_fn: Callable[..., Any],
    extra_skill_roots: Optional[Sequence[str | Path]],
    render_workspace_prompt_addendum_runtime_fn: Callable[..., str],
) -> str:
    return render_workspace_prompt_addendum_runtime_fn(
        cwd,
        build_workspace_prompt_context_fn=build_workspace_prompt_context_fn,
        extra_skill_roots=extra_skill_roots,
    )


def build_workspace_reference_snapshot(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]],
    max_chars: int,
    build_workspace_prompt_context_fn: Callable[..., Any],
    safe_resolve: Callable[[str | Path], Path],
    text_digest: Callable[[str], str],
    discover_project_doc_paths_fn: Callable[[str | Path], list[Path]],
    path_signature: Callable[[Path], Dict[str, Any]],
    workspace_trust_level_fn: Callable[[str | Path], str],
    build_workspace_reference_snapshot_runtime_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    return build_workspace_reference_snapshot_runtime_fn(
        cwd,
        extra_skill_roots=extra_skill_roots,
        max_chars=max_chars,
        build_workspace_prompt_context_fn=build_workspace_prompt_context_fn,
        safe_resolve=safe_resolve,
        text_digest=text_digest,
        discover_project_doc_paths_fn=discover_project_doc_paths_fn,
        path_signature=path_signature,
        workspace_trust_level_fn=workspace_trust_level_fn,
    )


def render_explicit_skill_injections(
    text: str,
    skills: list[Any] | str | Path | None,
    *,
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], list[Any]],
    explicitly_mentioned_skills_fn: Callable[[str, list[Any]], list[Any]],
    extra_skill_roots: Optional[Sequence[str | Path]],
    render_explicit_skill_injections_runtime_fn: Callable[..., Optional[str]],
) -> Optional[str]:
    return render_explicit_skill_injections_runtime_fn(
        text,
        skills,
        discover_workspace_skills_fn=lambda resolved_cwd, roots: discover_workspace_skills_fn(
            resolved_cwd,
            roots,
        ),
        explicitly_mentioned_skills_fn=explicitly_mentioned_skills_fn,
        extra_skill_roots=extra_skill_roots,
    )
