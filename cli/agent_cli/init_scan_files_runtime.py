from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path | None, *, max_bytes: int) -> str:
    if path is None or not path.is_file() or max_bytes <= 0:
        return ""
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace").strip()


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def known_files(project_root: Path, names: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for name in names:
        candidate = project_root / name
        if candidate.is_file():
            items.append(relpath(candidate, project_root))
    return items


def known_relative_paths(project_root: Path, names: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for name in names:
        candidate = project_root / name
        if candidate.is_file():
            items.append(relpath(candidate, project_root))
    return items


def ci_files(project_root: Path) -> list[str]:
    items: list[str] = []
    workflows_dir = project_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for child in sorted(workflows_dir.iterdir()):
            if child.is_file() and child.suffix.lower() in {".yml", ".yaml"}:
                items.append(relpath(child, project_root))
    for name in (".gitlab-ci.yml", "azure-pipelines.yml"):
        candidate = project_root / name
        if candidate.is_file():
            items.append(relpath(candidate, project_root))
    return items


def rule_files(project_root: Path, rel_dir: str) -> list[str]:
    root = project_root / rel_dir
    if not root.is_dir():
        return []
    items: list[str] = []
    for child in sorted(root.rglob("*.md")):
        if child.is_file():
            items.append(relpath(child, project_root))
    return items


def rule_paths_from_roots(project_root: Path, rel_dirs: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for rel_dir in rel_dirs:
        items.extend(rule_files(project_root, rel_dir))
    return items


def skill_files(project_root: Path, rel_dir: str = ".agents/skills") -> list[str]:
    root = project_root / rel_dir
    if not root.is_dir():
        return []
    items: list[str] = []
    for child in sorted(root.rglob("SKILL.md")):
        if child.is_file():
            items.append(relpath(child, project_root))
    return items
