from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cli.agent_cli.runtime_paths import PROJECT_LOCAL_DATA_DIR_CANDIDATES
from cli.agent_cli import workspace_context_facade_runtime as workspace_context_facade_runtime_helpers
from cli.agent_cli import workspace_context_config_runtime as workspace_context_config_runtime_service
from cli.agent_cli import workspace_context_assembly_runtime as workspace_context_assembly_runtime_helpers
from cli.agent_cli import workspace_context_private_runtime as workspace_context_private_runtime_helpers
from cli.agent_cli import workspace_context_projection_runtime as workspace_context_projection_runtime_helpers
from cli.agent_cli import workspace_context_runtime_helpers_bridge as workspace_context_runtime_bridge_helpers
from cli.agent_cli import workspace_context_runtime_skill_helpers

DEFAULT_PROJECT_DOC_FILENAME = "AENGTHUB.md"
LOCAL_PROJECT_DOC_FILENAME = "AENGTHUB.override.md"
LEGACY_PROJECT_DOC_FILENAMES = ("AGENTS.md",)
LEGACY_LOCAL_PROJECT_DOC_FILENAMES = ("AGENTS.override.md",)
DEFAULT_PROJECT_ROOT_MARKERS = (".git",)
AGENTS_DIRNAME = ".agents"
LEGACY_REPO_CONFIG_DIRNAME = ".agent_cli_legacy"
SKILLS_DIRNAME = "skills"
SKILL_FILENAME = "SKILL.md"
DEFAULT_PROJECT_DOC_MAX_BYTES = 16 * 1024
DEFAULT_WORKSPACE_CONTEXT_MAX_CHARS = 16 * 1024
DEFAULT_WORKSPACE_CONTEXT_UPDATE_MAX_CHARS = 6 * 1024
MAX_SKILL_SCAN_DEPTH = 6
AGENT_CLI_HOME = Path(os.environ.get("AGENT_CLI_HOME") or (Path.home() / ".agent_cli"))
LEGACY_COMPAT_HOME = Path.home() / ".agent_cli_legacy"
AGENT_CLI_CONFIG_TOML = AGENT_CLI_HOME / "config.toml"
AGENT_CLI_AUTH_JSON = AGENT_CLI_HOME / "auth.json"

@dataclass(frozen=True)
class WorkspaceSkill:
    name: str
    description: str
    path: Path

@dataclass(frozen=True)
class WorkspacePromptContext:
    instructions_text: str = ""
    skills: List[WorkspaceSkill] = field(default_factory=list)

def merge_nested_mappings(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    return workspace_context_private_runtime_helpers.merge_nested_mappings(base, override)

_safe_resolve = workspace_context_private_runtime_helpers.safe_resolve
_read_toml = workspace_context_private_runtime_helpers.read_toml
_read_json = workspace_context_private_runtime_helpers.read_json

def _workspace_config_candidates(cwd: Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> List[Path]:
    return workspace_context_facade_runtime_helpers.workspace_config_candidates(cwd, workspace_config_candidates_runtime_fn=workspace_context_assembly_runtime_helpers.workspace_config_candidates, safe_resolve=_safe_resolve, project_local_data_dir_candidates=PROJECT_LOCAL_DATA_DIR_CANDIDATES, agent_cli_home=AGENT_CLI_HOME, legacy_compat_home=LEGACY_COMPAT_HOME, home_config_paths=home_config_paths)

def _existing_home_config_paths(*, home_config_paths: Optional[Sequence[Path]] = None) -> List[Path]:
    return workspace_context_facade_runtime_helpers.existing_home_config_paths(existing_home_config_paths_runtime_fn=workspace_context_assembly_runtime_helpers.existing_home_config_paths, safe_resolve=_safe_resolve, agent_cli_home=AGENT_CLI_HOME, legacy_compat_home=LEGACY_COMPAT_HOME, home_config_paths=home_config_paths)

def _merged_home_workspace_config(*, home_config_paths: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    return workspace_context_facade_runtime_helpers.merged_home_workspace_config(merged_home_workspace_config_runtime_fn=workspace_context_assembly_runtime_helpers.merged_home_workspace_config, merge_nested_mappings=merge_nested_mappings, existing_home_config_paths_fn=_existing_home_config_paths, read_toml_fn=_read_toml, agent_cli_home=AGENT_CLI_HOME, legacy_compat_home=LEGACY_COMPAT_HOME, home_config_paths=home_config_paths)

def _config_list(config: Dict[str, Any], key: str) -> Optional[List[str]]:
    return workspace_context_private_runtime_helpers.config_list(config, key)

def _merged_workspace_config(cwd: str | Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    return workspace_context_facade_runtime_helpers.merged_workspace_config(cwd, merged_workspace_config_runtime_fn=workspace_context_assembly_runtime_helpers.merged_workspace_config, safe_resolve=_safe_resolve, workspace_config_candidates_fn=_workspace_config_candidates, merge_nested_mappings=merge_nested_mappings, read_toml_fn=_read_toml, agent_cli_home=AGENT_CLI_HOME, legacy_compat_home=LEGACY_COMPAT_HOME, home_config_paths=home_config_paths)

def workspace_trust_level(cwd: str | Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> str:
    return workspace_context_assembly_runtime_helpers.workspace_trust_level(cwd, safe_resolve=_safe_resolve, merged_home_workspace_config_fn=_merged_home_workspace_config, home_config_paths=home_config_paths)

def project_root_markers(cwd: str | Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> List[str]:
    items = _config_list(_merged_workspace_config(cwd, home_config_paths=home_config_paths), "project_root_markers")
    if items is None:
        return list(DEFAULT_PROJECT_ROOT_MARKERS)
    return items

def project_doc_fallback_filenames(cwd: str | Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> List[str]:
    configured = _config_list(
        _merged_workspace_config(cwd, home_config_paths=home_config_paths),
        "project_doc_fallback_filenames",
    ) or []
    return workspace_context_runtime_bridge_helpers.project_doc_fallback_filenames_from_config(
        configured=configured,
        default_project_doc_filename=DEFAULT_PROJECT_DOC_FILENAME,
        local_project_doc_filename=LOCAL_PROJECT_DOC_FILENAME,
        legacy_local_project_doc_filenames=LEGACY_LOCAL_PROJECT_DOC_FILENAMES,
        legacy_project_doc_filenames=LEGACY_PROJECT_DOC_FILENAMES,
    )

def find_project_root(cwd: str | Path, markers: Iterable[str]) -> Path:
    return workspace_context_assembly_runtime_helpers.find_project_root(cwd, markers, safe_resolve=_safe_resolve)

def dirs_between_project_root_and_cwd(cwd: str | Path, project_root: str | Path) -> List[Path]:
    return workspace_context_assembly_runtime_helpers.dirs_between_project_root_and_cwd(cwd, project_root, safe_resolve=_safe_resolve)

def discover_project_doc_paths(cwd: str | Path, *, home_config_paths: Optional[Sequence[Path]] = None) -> List[Path]:
    return workspace_context_runtime_bridge_helpers.discover_project_doc_paths(
        cwd,
        discover_project_doc_paths_runtime_fn=workspace_context_assembly_runtime_helpers.discover_project_doc_paths,
        safe_resolve=_safe_resolve,
        project_root_markers_fn=project_root_markers,
        find_project_root_fn=find_project_root,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd,
        project_doc_fallback_filenames_fn=project_doc_fallback_filenames,
        local_project_doc_filename=LOCAL_PROJECT_DOC_FILENAME,
        default_project_doc_filename=DEFAULT_PROJECT_DOC_FILENAME,
        home_config_paths=home_config_paths,
    )

def read_project_docs(
    cwd: str | Path,
    *,
    max_total_bytes: int = DEFAULT_PROJECT_DOC_MAX_BYTES,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Optional[str]:
    return workspace_context_runtime_bridge_helpers.read_project_docs(
        cwd,
        read_project_docs_runtime_fn=workspace_context_config_runtime_service.read_project_docs,
        discover_project_doc_paths_fn=discover_project_doc_paths,
        max_total_bytes=max_total_bytes,
        home_config_paths=home_config_paths,
    )

def _parse_skill_file(path: Path) -> Optional[WorkspaceSkill]:
    return workspace_context_runtime_skill_helpers.parse_skill_file(path, safe_resolve_fn=_safe_resolve, skill_factory=WorkspaceSkill)

def _repo_skill_roots(cwd: Path, project_root: Path, markers: List[str]) -> List[Path]:
    return workspace_context_runtime_skill_helpers.repo_skill_roots(cwd, project_root, markers, dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd, safe_resolve_fn=_safe_resolve, agents_dirname=AGENTS_DIRNAME, legacy_repo_config_dirname=LEGACY_REPO_CONFIG_DIRNAME, skills_dirname=SKILLS_DIRNAME)

def discover_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    home_config_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    return workspace_context_runtime_bridge_helpers.discover_project_local_paths(
        filename,
        cwd=cwd,
        discover_project_local_paths_runtime_fn=workspace_context_assembly_runtime_helpers.discover_project_local_paths,
        safe_resolve=_safe_resolve,
        workspace_trust_level_fn=workspace_trust_level,
        project_root_markers_fn=project_root_markers,
        find_project_root_fn=find_project_root,
        dirs_between_project_root_and_cwd_fn=dirs_between_project_root_and_cwd,
        project_local_data_dir_candidates=PROJECT_LOCAL_DATA_DIR_CANDIDATES,
        home_config_paths=home_config_paths,
    )

def read_merged_project_toml(
    *,
    cwd: str | Path,
    filename: str = "config.toml",
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Tuple[Dict[str, Any], List[Path]]:
    return workspace_context_runtime_bridge_helpers.read_merged_project_file_configs(
        cwd=cwd,
        filename=filename,
        merge_project_file_configs_runtime_fn=workspace_context_assembly_runtime_helpers.merge_project_file_configs,
        discover_project_local_paths_fn=discover_project_local_paths,
        safe_resolve=_safe_resolve,
        merge_nested_mappings=merge_nested_mappings,
        reader_fn=_read_toml,
        home_config_paths=home_config_paths,
    )

def read_merged_project_json(
    *,
    cwd: str | Path,
    filename: str = "auth.json",
    home_config_paths: Optional[Sequence[Path]] = None,
) -> Tuple[Dict[str, Any], List[Path]]:
    return workspace_context_runtime_bridge_helpers.read_merged_project_file_configs(
        cwd=cwd,
        filename=filename,
        merge_project_file_configs_runtime_fn=workspace_context_assembly_runtime_helpers.merge_project_file_configs,
        discover_project_local_paths_fn=discover_project_local_paths,
        safe_resolve=_safe_resolve,
        merge_nested_mappings=merge_nested_mappings,
        reader_fn=_read_json,
        home_config_paths=home_config_paths,
    )

def discover_repo_skills(cwd: str | Path) -> List[WorkspaceSkill]:
    return workspace_context_runtime_skill_helpers.discover_repo_skills(cwd, safe_resolve_fn=_safe_resolve, project_root_markers_fn=project_root_markers, find_project_root_fn=find_project_root, repo_skill_roots_fn=_repo_skill_roots, discover_skills_from_roots_fn=discover_skills_from_roots)

def discover_skills_from_roots(
    skill_roots: Sequence[str | Path],
    *,
    include_hidden: bool = False,
) -> List[WorkspaceSkill]:
    return workspace_context_runtime_skill_helpers.discover_skills_from_roots(
        skill_roots,
        safe_resolve_fn=_safe_resolve,
        skill_filename=SKILL_FILENAME,
        max_skill_scan_depth=MAX_SKILL_SCAN_DEPTH,
        parse_skill_file_fn=_parse_skill_file,
        include_hidden=include_hidden,
    )

def agent_cli_home_skill_roots() -> List[str]:
    candidate = _safe_resolve(AGENT_CLI_HOME / SKILLS_DIRNAME)
    if not candidate.is_dir():
        return []
    return [str(candidate)]

def discover_workspace_skills(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> List[WorkspaceSkill]:
    return workspace_context_runtime_skill_helpers.discover_workspace_skills(cwd, discover_repo_skills_fn=discover_repo_skills, discover_skills_from_roots_fn=discover_skills_from_roots, extra_skill_roots=extra_skill_roots)

def render_skills_section(skills: List[WorkspaceSkill]) -> Optional[str]:
    return workspace_context_runtime_skill_helpers.render_skills_section(skills, skill_usage_rules=workspace_context_facade_runtime_helpers.SKILL_USAGE_RULES)

def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> WorkspacePromptContext:
    return workspace_context_runtime_bridge_helpers.build_workspace_prompt_context(
        cwd,
        build_workspace_prompt_context_runtime_fn=workspace_context_projection_runtime_helpers.build_workspace_prompt_context,
        safe_resolve=_safe_resolve,
        read_project_docs_fn=read_project_docs,
        discover_workspace_skills_fn=discover_workspace_skills,
        render_skills_section_fn=render_skills_section,
        context_factory=WorkspacePromptContext,
        empty_context_factory=WorkspacePromptContext,
        extra_skill_roots=extra_skill_roots,
    )

def render_workspace_prompt_addendum(
    cwd: str | Path | None = None,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> str:
    return workspace_context_facade_runtime_helpers.render_workspace_prompt_addendum(cwd, render_workspace_prompt_addendum_runtime_fn=workspace_context_projection_runtime_helpers.render_workspace_prompt_addendum, build_workspace_prompt_context_fn=build_workspace_prompt_context, extra_skill_roots=extra_skill_roots)

_text_digest = workspace_context_private_runtime_helpers.text_digest
_json_digest = workspace_context_private_runtime_helpers.json_digest

def _path_signature(path: Path) -> Dict[str, Any]:
    return workspace_context_private_runtime_helpers.path_signature(path, safe_resolve_fn=_safe_resolve)

def workspace_context_marker_offset(text: str) -> int | None:
    return workspace_context_projection_runtime_helpers.workspace_context_marker_offset(text)

def workspace_contract(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    return workspace_context_projection_runtime_helpers.workspace_contract(snapshot)

def build_workspace_reference_snapshot(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
    max_chars: int = DEFAULT_WORKSPACE_CONTEXT_MAX_CHARS,
) -> Dict[str, Any]:
    return workspace_context_facade_runtime_helpers.build_workspace_reference_snapshot(cwd, build_workspace_reference_snapshot_runtime_fn=workspace_context_assembly_runtime_helpers.build_workspace_reference_snapshot, extra_skill_roots=extra_skill_roots, max_chars=max_chars, build_workspace_prompt_context_fn=build_workspace_prompt_context, safe_resolve=_safe_resolve, text_digest=_text_digest, discover_project_doc_paths_fn=discover_project_doc_paths, path_signature=_path_signature, workspace_trust_level_fn=workspace_trust_level)

def workspace_reference_diff(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> Dict[str, Any]:
    return workspace_context_projection_runtime_helpers.workspace_reference_diff(previous, current)

def render_workspace_context_update_message(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int = DEFAULT_WORKSPACE_CONTEXT_UPDATE_MAX_CHARS,
) -> Optional[str]:
    return workspace_context_projection_runtime_helpers.render_workspace_context_update_message(previous, current, max_chars=max_chars)

def _workspace_instructions_excerpt(
    current: Dict[str, Any],
    *,
    max_chars: int = DEFAULT_WORKSPACE_CONTEXT_UPDATE_MAX_CHARS,
) -> str:
    return workspace_context_private_runtime_helpers.workspace_instructions_excerpt(current, max_chars=max_chars)

def build_workspace_reference_context_item(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    return workspace_context_projection_runtime_helpers.build_workspace_reference_context_item(previous, current, max_chars=DEFAULT_WORKSPACE_CONTEXT_UPDATE_MAX_CHARS)

def render_workspace_reference_context_item_message(item: Dict[str, Any]) -> Optional[str]:
    return workspace_context_projection_runtime_helpers.render_workspace_reference_context_item_message(item)

def explicitly_mentioned_skills(text: str, skills: List[WorkspaceSkill]) -> List[WorkspaceSkill]:
    return workspace_context_runtime_skill_helpers.explicitly_mentioned_skills(text, skills)

def render_explicit_skill_injections(
    text: str,
    skills: List[WorkspaceSkill] | str | Path | None,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Optional[str]:
    return workspace_context_runtime_bridge_helpers.render_explicit_skill_injections(
        text,
        skills,
        render_explicit_skill_injections_runtime_fn=workspace_context_assembly_runtime_helpers.render_explicit_skill_injections,
        discover_workspace_skills_fn=discover_workspace_skills,
        explicitly_mentioned_skills_fn=explicitly_mentioned_skills,
        extra_skill_roots=extra_skill_roots,
    )
