from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any


def scan_languages_from_tree(
    project_root: Path,
    *,
    ignored_dirs: set[str],
    extension_language_map: dict[str, str],
    max_files: int = 2000,
    max_depth: int = 4,
) -> list[str]:
    counter: Counter[str] = Counter()
    seen = 0
    for current_root, dir_names, file_names in os.walk(project_root):
        current_path = Path(current_root)
        try:
            relative_depth = len(current_path.relative_to(project_root).parts)
        except ValueError:
            relative_depth = 0
        dir_names[:] = [
            item
            for item in dir_names
            if item not in ignored_dirs and relative_depth < max_depth
        ]
        for file_name in file_names:
            suffix = Path(file_name).suffix.lower()
            language = extension_language_map.get(suffix)
            if language:
                counter[language] += 1
            seen += 1
            if seen >= max_files:
                break
        if seen >= max_files:
            break
    return [name for name, _count in counter.most_common()]


def frameworks_from_mapping(dependencies: set[str], mapping: dict[str, str]) -> list[str]:
    items: list[str] = []
    for dependency_name, framework_name in mapping.items():
        if dependency_name in dependencies:
            items.append(framework_name)
    return items


def node_dependencies(package_json: dict[str, Any]) -> set[str]:
    dependencies: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        payload = package_json.get(key)
        if not isinstance(payload, dict):
            continue
        dependencies.update(str(name).strip() for name in payload.keys() if str(name).strip())
    return dependencies


def python_dependencies(
    pyproject: dict[str, Any],
    project_root: Path,
    *,
    normalize_requirement_entries: Any,
    read_text: Any,
) -> set[str]:
    dependencies: set[str] = set()
    project_section = pyproject.get("project")
    if isinstance(project_section, dict):
        dependencies.update(normalize_requirement_entries(project_section.get("dependencies")))
        optional_dependencies = project_section.get("optional-dependencies")
        if isinstance(optional_dependencies, dict):
            for value in optional_dependencies.values():
                dependencies.update(normalize_requirement_entries(value))
    tool_section = pyproject.get("tool")
    if isinstance(tool_section, dict):
        poetry_section = tool_section.get("poetry")
        if isinstance(poetry_section, dict):
            direct_deps = poetry_section.get("dependencies")
            if isinstance(direct_deps, dict):
                dependencies.update(
                    str(name).strip()
                    for name in direct_deps.keys()
                    if str(name).strip() and str(name).strip() != "python"
                )
            group_payload = poetry_section.get("group")
            if isinstance(group_payload, dict):
                for value in group_payload.values():
                    if not isinstance(value, dict):
                        continue
                    group_deps = value.get("dependencies")
                    if isinstance(group_deps, dict):
                        dependencies.update(
                            str(name).strip()
                            for name in group_deps.keys()
                            if str(name).strip() and str(name).strip() != "python"
                        )
        for tool_name in ("ruff", "black", "pytest", "mypy"):
            if tool_name in tool_section:
                dependencies.add(tool_name)
    requirements_text = read_text(project_root / "requirements.txt", max_bytes=8 * 1024)
    if requirements_text:
        dependencies.update(normalize_requirement_entries(requirements_text.splitlines()))
    return dependencies


def cargo_dependencies(cargo_toml: dict[str, Any]) -> set[str]:
    dependencies: set[str] = set()
    for key in ("dependencies", "dev-dependencies"):
        payload = cargo_toml.get(key)
        if isinstance(payload, dict):
            dependencies.update(str(name).strip() for name in payload.keys() if str(name).strip())
    workspace = cargo_toml.get("workspace")
    if isinstance(workspace, dict):
        workspace_deps = workspace.get("dependencies")
        if isinstance(workspace_deps, dict):
            dependencies.update(str(name).strip() for name in workspace_deps.keys() if str(name).strip())
    return dependencies


def normalize_requirement_entries(value: Any, *, requirement_name_pattern: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    normalized: set[str] = set()
    for entry in value:
        text = str(entry or "").strip()
        if not text:
            continue
        match = requirement_name_pattern.match(text)
        if match:
            normalized.add(match.group(1).lower())
    return normalized


def package_managers_from_repo(
    project_root: Path,
    *,
    package_json: dict[str, Any],
    pyproject: dict[str, Any],
    cargo_toml: dict[str, Any],
    go_mod_text: str,
    package_manager_lockfiles: tuple[tuple[str, str], ...],
    unique: Any,
) -> list[str]:
    managers: list[str] = []
    package_manager_text = str(package_json.get("packageManager") or "").strip()
    if package_manager_text:
        managers.append(package_manager_text.split("@", 1)[0])
    for filename, manager_name in package_manager_lockfiles:
        if (project_root / filename).exists():
            managers.append(manager_name)
    if package_json:
        managers.append("npm")
    if pyproject or (project_root / "requirements.txt").is_file():
        if (project_root / "uv.lock").exists():
            managers.append("uv")
        elif (project_root / "poetry.lock").exists():
            managers.append("poetry")
        elif (project_root / "pdm.lock").exists():
            managers.append("pdm")
        else:
            managers.append("pip")
    if cargo_toml:
        managers.append("cargo")
    if go_mod_text:
        managers.append("go")
    return unique(managers)


def primary_node_manager(package_managers: list[str]) -> str:
    for candidate in ("pnpm", "yarn", "bun", "npm"):
        if candidate in package_managers:
            return candidate
    return ""


def script_commands(manager: str, scripts: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    commands: list[str] = []
    for name in names:
        if name not in scripts:
            continue
        if manager == "npm":
            commands.append(f"npm run {name}")
        elif manager == "pnpm":
            commands.append(f"pnpm {name}")
        elif manager == "yarn":
            commands.append(f"yarn {name}")
        elif manager == "bun":
            commands.append(f"bun run {name}")
    return commands


def python_runner_prefix(package_managers: list[str]) -> str:
    if "uv" in package_managers:
        return "uv run"
    if "poetry" in package_managers:
        return "poetry run"
    if "pdm" in package_managers:
        return "pdm run"
    return ""


def python_command(prefix: str, command: str) -> str:
    return f"{prefix} {command}".strip()


def make_targets(
    path: Path,
    *,
    read_text: Any,
    make_target_pattern: Any,
    unique: Any,
) -> list[str]:
    text = read_text(path, max_bytes=12 * 1024)
    if not text:
        return []
    targets: list[str] = []
    for line in text.splitlines():
        if line.startswith("\t") or line.startswith(" "):
            continue
        match = make_target_pattern.match(line)
        if not match:
            continue
        target = str(match.group(1) or "").strip()
        if target and not target.startswith("."):
            targets.append(target)
    return unique(targets)
