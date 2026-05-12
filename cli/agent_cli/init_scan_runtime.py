from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cli.agent_cli import init_scan_files_runtime as init_scan_files_runtime_service
from cli.agent_cli import init_scan_runtime_command_groups_helpers as command_groups_helpers
from cli.agent_cli import init_scan_runtime_helpers as init_scan_helpers
from cli.agent_cli.workspace_context import (
    DEFAULT_PROJECT_DOC_FILENAME,
    LEGACY_LOCAL_PROJECT_DOC_FILENAMES,
    LEGACY_PROJECT_DOC_FILENAMES,
    LOCAL_PROJECT_DOC_FILENAME,
    find_project_root,
    project_root_markers,
)

_README_FILENAMES = ("README.md", "README.rst", "README.txt")
_MANIFEST_FILENAMES = (
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "Makefile",
)
_AI_INSTRUCTION_FILENAMES = (
    DEFAULT_PROJECT_DOC_FILENAME,
    LOCAL_PROJECT_DOC_FILENAME,
    *LEGACY_PROJECT_DOC_FILENAMES,
    *LEGACY_LOCAL_PROJECT_DOC_FILENAMES,
    "CLAUDE.md",
    "GEMINI.md",
    "COPILOT.md",
)
_EXTRA_AI_INSTRUCTION_PATHS = (
    ".github/copilot-instructions.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
)
_EXTRA_AI_RULE_DIRS = (".agenthub/rules", ".cursor/rules")
_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    ".turbo",
    "target",
}
_EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
}
_NODE_FRAMEWORK_MAP = {
    "next": "next.js",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "vite": "vite",
    "express": "express",
    "nest": "nestjs",
}
_PYTHON_FRAMEWORK_MAP = {
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "pytest": "pytest",
    "ruff": "ruff",
    "black": "black",
}
_RUST_FRAMEWORK_MAP = {
    "tokio": "tokio",
    "axum": "axum",
    "actix-web": "actix-web",
    "tauri": "tauri",
}
_PACKAGE_MANAGER_LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("package-lock.json", "npm"),
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("pdm.lock", "pdm"),
)
_REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_MAKE_TARGET_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")


def build_init_scan_summary(cwd: str | Path) -> dict[str, Any]:
    resolved_cwd = Path(cwd).resolve()
    project_root = resolve_init_project_root(resolved_cwd)
    project_doc_path = project_root / DEFAULT_PROJECT_DOC_FILENAME
    local_doc_path = project_root / LOCAL_PROJECT_DOC_FILENAME
    legacy_project_path = next(
        (
            project_root / name
            for name in LEGACY_PROJECT_DOC_FILENAMES
            if (project_root / name).is_file()
        ),
        None,
    )
    legacy_local_path = next(
        (
            project_root / name
            for name in LEGACY_LOCAL_PROJECT_DOC_FILENAMES
            if (project_root / name).is_file()
        ),
        None,
    )
    readme_paths = _known_files(project_root, _README_FILENAMES)
    manifest_paths = _known_files(project_root, _MANIFEST_FILENAMES)
    ci_paths = _ci_files(project_root)
    rule_paths = _rule_files(project_root, ".agenthub/rules")
    skill_paths = _skill_files(project_root)
    ai_instruction_sources = _unique(
        [
            *_known_files(project_root, _AI_INSTRUCTION_FILENAMES),
            *_known_relative_paths(project_root, _EXTRA_AI_INSTRUCTION_PATHS),
            *_rule_paths_from_roots(project_root, _EXTRA_AI_RULE_DIRS),
            *skill_paths,
        ]
    )

    package_json = _read_json(project_root / "package.json")
    pyproject = _read_toml(project_root / "pyproject.toml")
    cargo_toml = _read_toml(project_root / "Cargo.toml")
    go_mod_text = _read_text(project_root / "go.mod", max_bytes=8 * 1024)
    make_targets = _make_targets(project_root / "Makefile")
    extension_languages = _scan_languages_from_tree(project_root)

    languages = _unique(
        [
            *_node_languages(package_json, project_root),
            *_python_languages(pyproject, project_root),
            *_rust_languages(cargo_toml),
            *_go_languages(go_mod_text),
            *extension_languages,
        ]
    )
    frameworks = _unique(
        [
            *_frameworks_from_mapping(_node_dependencies(package_json), _NODE_FRAMEWORK_MAP),
            *_frameworks_from_mapping(
                _python_dependencies(pyproject, project_root), _PYTHON_FRAMEWORK_MAP
            ),
            *_frameworks_from_mapping(_cargo_dependencies(cargo_toml), _RUST_FRAMEWORK_MAP),
        ]
    )
    package_managers = _package_managers_from_repo(
        project_root, package_json, pyproject, cargo_toml, go_mod_text
    )
    command_groups = _build_command_groups(
        project_root,
        package_json=package_json,
        pyproject=pyproject,
        cargo_toml=cargo_toml,
        go_mod_text=go_mod_text,
        make_targets=make_targets,
        package_managers=package_managers,
    )

    gitignore_path = project_root / ".gitignore"
    return {
        "project_root": str(project_root),
        "project_name": str(project_root.name or project_root),
        "cwd": str(resolved_cwd),
        "project_doc_path": str(project_doc_path),
        "local_doc_path": str(local_doc_path),
        "existing_project_doc_path": str(project_doc_path) if project_doc_path.is_file() else "",
        "existing_local_doc_path": str(local_doc_path) if local_doc_path.is_file() else "",
        "legacy_project_doc_path": str(legacy_project_path) if legacy_project_path else "",
        "legacy_local_doc_path": str(legacy_local_path) if legacy_local_path else "",
        "existing_project_doc_text": _read_text(project_doc_path, max_bytes=16 * 1024),
        "existing_local_doc_text": _read_text(local_doc_path, max_bytes=8 * 1024),
        "legacy_project_doc_text": (
            _read_text(legacy_project_path, max_bytes=16 * 1024) if legacy_project_path else ""
        ),
        "legacy_local_doc_text": (
            _read_text(legacy_local_path, max_bytes=8 * 1024) if legacy_local_path else ""
        ),
        "readme_paths": readme_paths,
        "manifest_paths": manifest_paths,
        "ci_paths": ci_paths,
        "rule_paths": rule_paths,
        "skill_paths": skill_paths,
        "ai_instruction_sources": ai_instruction_sources,
        "gitignore_path": (
            _relpath(gitignore_path, project_root) if gitignore_path.is_file() else ""
        ),
        "gitignore_text": _read_text(gitignore_path, max_bytes=8 * 1024),
        "readme_excerpt": (
            _read_text(project_root / readme_paths[0], max_bytes=4 * 1024) if readme_paths else ""
        ),
        "languages": languages,
        "frameworks": frameworks,
        "package_managers": package_managers,
        "command_groups": command_groups,
        "make_targets": make_targets,
    }


def resolve_init_project_root(cwd: str | Path) -> Path:
    resolved = Path(cwd).resolve()
    markers = project_root_markers(resolved)
    return find_project_root(resolved, markers)


_read_json = init_scan_files_runtime_service.read_json
_read_toml = init_scan_files_runtime_service.read_toml
_read_text = init_scan_files_runtime_service.read_text
_known_files = init_scan_files_runtime_service.known_files
_known_relative_paths = init_scan_files_runtime_service.known_relative_paths
_ci_files = init_scan_files_runtime_service.ci_files
_rule_files = init_scan_files_runtime_service.rule_files
_rule_paths_from_roots = init_scan_files_runtime_service.rule_paths_from_roots
_skill_files = init_scan_files_runtime_service.skill_files
_relpath = init_scan_files_runtime_service.relpath


def _scan_languages_from_tree(
    project_root: Path, *, max_files: int = 2000, max_depth: int = 4
) -> list[str]:
    return init_scan_helpers.scan_languages_from_tree(
        project_root,
        ignored_dirs=_IGNORED_DIRS,
        extension_language_map=_EXTENSION_LANGUAGE_MAP,
        max_files=max_files,
        max_depth=max_depth,
    )


def _node_languages(package_json: dict[str, Any], project_root: Path) -> list[str]:
    if not package_json and not (project_root / "package.json").is_file():
        return []
    deps = _node_dependencies(package_json)
    if "typescript" in deps or (project_root / "tsconfig.json").is_file():
        return ["typescript", "javascript"]
    return ["javascript"]


def _python_languages(pyproject: dict[str, Any], project_root: Path) -> list[str]:
    if pyproject or (project_root / "requirements.txt").is_file():
        return ["python"]
    return []


def _rust_languages(cargo_toml: dict[str, Any]) -> list[str]:
    return ["rust"] if cargo_toml else []


def _go_languages(go_mod_text: str) -> list[str]:
    return ["go"] if go_mod_text else []


def _frameworks_from_mapping(dependencies: set[str], mapping: dict[str, str]) -> list[str]:
    return init_scan_helpers.frameworks_from_mapping(dependencies, mapping)


def _node_dependencies(package_json: dict[str, Any]) -> set[str]:
    return init_scan_helpers.node_dependencies(package_json)


def _python_dependencies(pyproject: dict[str, Any], project_root: Path) -> set[str]:
    return init_scan_helpers.python_dependencies(
        pyproject,
        project_root,
        normalize_requirement_entries=_normalize_requirement_entries,
        read_text=_read_text,
    )


def _cargo_dependencies(cargo_toml: dict[str, Any]) -> set[str]:
    return init_scan_helpers.cargo_dependencies(cargo_toml)


def _normalize_requirement_entries(value: Any) -> set[str]:
    return init_scan_helpers.normalize_requirement_entries(
        value,
        requirement_name_pattern=_REQUIREMENT_NAME_PATTERN,
    )


def _package_managers_from_repo(
    project_root: Path,
    package_json: dict[str, Any],
    pyproject: dict[str, Any],
    cargo_toml: dict[str, Any],
    go_mod_text: str,
) -> list[str]:
    return init_scan_helpers.package_managers_from_repo(
        project_root,
        package_json=package_json,
        pyproject=pyproject,
        cargo_toml=cargo_toml,
        go_mod_text=go_mod_text,
        package_manager_lockfiles=_PACKAGE_MANAGER_LOCKFILES,
        unique=_unique,
    )


def _build_command_groups(
    project_root: Path,
    *,
    package_json: dict[str, Any],
    pyproject: dict[str, Any],
    cargo_toml: dict[str, Any],
    go_mod_text: str,
    make_targets: list[str],
    package_managers: list[str],
) -> dict[str, list[str]]:
    return command_groups_helpers.build_command_groups_impl(
        project_root,
        package_json=package_json,
        pyproject=pyproject,
        cargo_toml=cargo_toml,
        go_mod_text=go_mod_text,
        make_targets=make_targets,
        package_managers=package_managers,
        primary_node_manager_fn=_primary_node_manager,
        script_commands_fn=_script_commands,
        python_dependencies_fn=_python_dependencies,
        python_runner_prefix_fn=_python_runner_prefix,
        python_command_fn=_python_command,
        unique_fn=_unique,
    )


_primary_node_manager = init_scan_helpers.primary_node_manager
_script_commands = init_scan_helpers.script_commands
_python_runner_prefix = init_scan_helpers.python_runner_prefix
_python_command = init_scan_helpers.python_command


def _make_targets(path: Path) -> list[str]:
    return init_scan_helpers.make_targets(
        path,
        read_text=_read_text,
        make_target_pattern=_MAKE_TARGET_PATTERN,
        unique=_unique,
    )


def _unique(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items
