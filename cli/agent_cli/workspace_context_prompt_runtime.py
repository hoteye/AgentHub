from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_EMPTY_WORKSPACE_SCAFFOLD_RULE = "\n".join(
    [
        "## Workspace Defaults",
        "- If the current working directory is empty and the user asks you to create or scaffold a project or app, treat the current directory as the project root.",
        "- Do not create an extra top-level subdirectory named after the project or app unless the user explicitly asks for one.",
    ]
)


def _active_workspace_rules(cwd: Path) -> str:
    cwd_text = str(cwd).replace("\\", "/")
    return "\n".join(
        [
            "## Active Workspace",
            f"- Current working directory for local file tools: `{cwd_text}`",
            "- Treat that current working directory as the default base for local file tools.",
            "- For Glob/Grep-style directory filters, omit `path` or use `.` when the current working directory is the intended scope.",
            "- If repository-wide scope or a parent/sibling directory is needed, use an explicit local path that still stays inside the active workspace/project root.",
            "- When broader access is allowed, rely on the workspace_root surfaced in reference context instead of guessing a different boundary.",
            "- When the task is to locate a file anywhere in the current repository/workspace, prefer an explicit search path rooted at workspace_root.",
            "- Do not widen scope unless the task or referenced path actually requires it.",
        ]
    )


def extract_frontmatter(text: str) -> Optional[str]:
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    collected: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(collected)
        collected.append(line)
    return None


def parse_simple_frontmatter(text: str) -> Dict[str, str]:
    frontmatter = extract_frontmatter(text)
    if frontmatter is None:
        return {}
    payload: Dict[str, str] = {}
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value:
            payload[key] = value
    return payload


def parse_skill_file(
    path: Path,
    *,
    safe_resolve: Callable[[Path], Path],
    skill_factory: Callable[..., Any],
) -> Any | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    payload = parse_simple_frontmatter(text)
    if not payload:
        return None
    name = str(payload.get("name") or "").strip() or path.parent.name
    description = " ".join(str(payload.get("description") or "").strip().split())
    if not name or not description:
        return None
    return skill_factory(name=name, description=description, path=safe_resolve(path))


def repo_skill_roots(
    cwd: Path,
    project_root: Path,
    markers: Iterable[str],
    *,
    dirs_between_project_root_and_cwd: Callable[[str | Path, str | Path], List[Path]],
    safe_resolve: Callable[[Path], Path],
    agents_dirname: str,
    legacy_repo_config_dirname: str,
    skills_dirname: str,
) -> List[Path]:
    search_dirs = dirs_between_project_root_and_cwd(cwd, project_root) if list(markers) else [cwd]
    roots: List[Path] = []
    seen: set[Path] = set()
    for directory in search_dirs:
        for candidate in (
            directory / agents_dirname / skills_dirname,
            directory / legacy_repo_config_dirname / skills_dirname,
        ):
            if candidate.is_dir():
                normalized = safe_resolve(candidate)
                if normalized not in seen:
                    seen.add(normalized)
                    roots.append(normalized)
    return roots


def discover_skills_from_roots(
    skill_roots: Sequence[str | Path],
    *,
    safe_resolve: Callable[[Path], Path],
    skill_filename: str,
    max_skill_scan_depth: int,
    parse_skill_file: Callable[[Path], Any | None],
    include_hidden: bool = False,
) -> List[Any]:
    seen_paths: set[Path] = set()
    skills: List[Any] = []
    for root in skill_roots:
        skill_root = safe_resolve(Path(root))
        if not skill_root.is_dir():
            continue
        try:
            discovered = sorted(skill_root.rglob(skill_filename))
        except OSError:
            continue
        for skill_path in discovered:
            relative_parts = skill_path.relative_to(skill_root).parts
            if len(relative_parts) < 2 or len(relative_parts) - 1 > max_skill_scan_depth:
                continue
            if not include_hidden and any(str(part).startswith(".") for part in relative_parts[:-1]):
                continue
            skill = parse_skill_file(skill_path)
            if skill is None or skill.path in seen_paths:
                continue
            seen_paths.add(skill.path)
            skills.append(skill)
    return sorted(skills, key=lambda item: (item.name, str(item.path)))


def discover_repo_skills(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_root_markers: Callable[[str | Path], List[str]],
    find_project_root: Callable[[str | Path, Iterable[str]], Path],
    repo_skill_roots: Callable[[Path, Path, List[str]], List[Path]],
    discover_skills_from_roots: Callable[[Sequence[str | Path]], List[Any]],
) -> List[Any]:
    resolved_cwd = safe_resolve(Path(cwd))
    markers = project_root_markers(resolved_cwd)
    root = find_project_root(resolved_cwd, markers)
    return discover_skills_from_roots(repo_skill_roots(resolved_cwd, root, markers))


def discover_workspace_skills(
    cwd: str | Path,
    *,
    discover_repo_skills: Callable[[str | Path], List[Any]],
    discover_skills_from_roots: Callable[[Sequence[str | Path]], List[Any]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> List[Any]:
    repo_skills = discover_repo_skills(cwd)
    if not extra_skill_roots:
        return repo_skills
    seen_paths = {item.path for item in repo_skills}
    skills = list(repo_skills)
    for skill in discover_skills_from_roots(extra_skill_roots, include_hidden=True):
        if skill.path in seen_paths:
            continue
        seen_paths.add(skill.path)
        skills.append(skill)
    return sorted(skills, key=lambda item: (item.name, str(item.path)))


def render_skills_section(skills: List[Any], *, skill_usage_rules: str) -> Optional[str]:
    if not skills:
        return None
    lines: List[str] = [
        "## Skills",
        "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.",
        "### Available skills",
    ]
    for skill in skills:
        lines.append(f"- {skill.name}: {skill.description} (file: {str(skill.path).replace(chr(92), '/')})")
    lines.extend(["### How to use skills", skill_usage_rules])
    return "\n".join(lines)


def _normalized_instruction_sources(
    payload: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().replace("\\", "/")
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        kind = str(item.get("kind") or "").strip().lower() or "doc"
        if kind not in {"doc", "rule", "unknown"}:
            kind = "unknown"
        scope = str(item.get("scope") or "").strip().lower() or "project"
        order_raw = item.get("order")
        try:
            order = int(order_raw)
        except (TypeError, ValueError):
            order = index
        normalized.append(
            {
                "path": path,
                "kind": kind,
                "scope": scope,
                "order": max(1, order),
            }
        )
    return sorted(normalized, key=lambda item: (int(item.get("order") or 0), str(item.get("path") or "")))


def normalize_instruction_payload(
    payload: str | Dict[str, Any] | None,
) -> Tuple[str, List[Dict[str, Any]]]:
    if isinstance(payload, dict):
        text = str(payload.get("text") or "").strip()
        return text, _normalized_instruction_sources(payload.get("sources"))
    return str(payload or "").strip(), []


def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    read_project_docs: Callable[[str | Path], Optional[str]],
    discover_workspace_skills: Callable[[str | Path, Optional[Sequence[str | Path]]], List[Any]],
    render_skills_section: Callable[[List[Any]], Optional[str]],
    context_factory: Callable[..., Any],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Any:
    resolved_cwd = safe_resolve(Path(cwd))
    docs_payload = read_project_docs(resolved_cwd)
    docs_text, instruction_sources = normalize_instruction_payload(docs_payload)
    skills = discover_workspace_skills(resolved_cwd, extra_skill_roots)
    parts: List[str] = [_active_workspace_rules(resolved_cwd)]
    if docs_text:
        parts.append(docs_text)
    else:
        parts.append(_EMPTY_WORKSPACE_SCAFFOLD_RULE)
    skills_section = render_skills_section(skills)
    if skills_section:
        parts.append(skills_section)
    context = context_factory(instructions_text="\n\n".join(parts).strip(), skills=skills)
    try:
        object.__setattr__(context, "instruction_sources", instruction_sources)
    except Exception:
        pass
    return context


def text_digest(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def json_digest(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    return hashlib.sha1(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def path_signature(path: Path, *, safe_resolve: Callable[[Path], Path]) -> Dict[str, Any]:
    try:
        stat = path.stat()
        size = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        size = 0
        mtime_ns = 0
        digest = ""
    return {
        "path": str(safe_resolve(path)).replace("\\", "/"),
        "size": size,
        "mtime_ns": mtime_ns,
        "content_digest": digest,
    }


def skill_name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", flags=re.IGNORECASE)


def explicitly_mentioned_skills(text: str, skills: List[Any]) -> List[Any]:
    source = str(text or "")
    selected: List[Any] = []
    seen: set[Path] = set()
    for skill in skills:
        if skill.path in seen:
            continue
        path_text = str(skill.path).replace("\\", "/")
        if f"${skill.name}" in source or path_text in source or skill_name_pattern(skill.name).search(source):
            selected.append(skill)
            seen.add(skill.path)
    return selected


def render_explicit_skill_injections(
    text: str,
    skills: List[Any] | str | Path | None,
    *,
    discover_workspace_skills: Callable[[str | Path, Optional[Sequence[str | Path]]], List[Any]],
    explicitly_mentioned_skills: Callable[[str, List[Any]], List[Any]],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Optional[str]:
    if skills is None:
        return None
    if isinstance(skills, (str, Path)):
        resolved_skills = discover_workspace_skills(skills, extra_skill_roots)
    else:
        resolved_skills = list(skills or [])
    selected = explicitly_mentioned_skills(text, resolved_skills)
    if not selected:
        return None
    sections: List[str] = ["SKILL_INSTRUCTIONS:"]
    for skill in selected:
        try:
            contents = skill.path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not contents:
            continue
        sections.extend(["", f"### {skill.name} | {str(skill.path).replace(chr(92), '/')}", contents])
    return "\n".join(sections).strip() or None
