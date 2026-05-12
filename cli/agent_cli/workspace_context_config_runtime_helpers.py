from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Callable


def extract_frontmatter(text: str) -> str | None:
    source = str(text or "")
    if not source.startswith("---"):
        return None
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    collected: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(collected)
        collected.append(line)
    return None


def strip_frontmatter(text: str) -> str:
    source = str(text or "")
    if not source.startswith("---"):
        return source
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return source
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        return "\n".join(lines[index + 1 :]).lstrip("\n")
    return source


def parse_frontmatter_value(text: str) -> str:
    return str(text or "").strip().strip("\"'")


def parse_rule_frontmatter(text: str) -> dict[str, Any]:
    frontmatter = extract_frontmatter(text)
    if frontmatter is None:
        return {}
    payload: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in frontmatter.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current_list_key and stripped.startswith("-"):
            value = parse_frontmatter_value(stripped[1:])
            if value:
                payload.setdefault(current_list_key, [])
                if isinstance(payload.get(current_list_key), list):
                    payload[current_list_key].append(value)
            continue
        if ":" not in stripped:
            current_list_key = None
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            current_list_key = None
            continue
        if key == "paths":
            current_list_key = "paths"
            if not value:
                payload["paths"] = []
                continue
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                items = [parse_frontmatter_value(item) for item in inner.split(",")]
                payload["paths"] = [item for item in items if item]
            else:
                normalized = parse_frontmatter_value(value)
                payload["paths"] = [normalized] if normalized else []
            continue
        payload[key] = parse_frontmatter_value(value)
        current_list_key = None
    return payload


def rule_enabled(payload: dict[str, Any]) -> bool:
    value = str(payload.get("enabled") or "").strip().lower()
    if not value:
        return True
    return value not in {"false", "0", "off", "no"}


def rule_priority(payload: dict[str, Any]) -> int:
    value = str(payload.get("priority") or "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def rule_paths(payload: dict[str, Any]) -> list[str]:
    values = payload.get("paths")
    if not isinstance(values, list):
        return []
    return [str(item or "").strip() for item in values if str(item or "").strip()]


def relative_cwd_path(cwd: Path, directory: Path) -> str:
    try:
        relative = cwd.relative_to(directory)
    except ValueError:
        return "."
    normalized = relative.as_posix().strip()
    return normalized or "."


def rule_matches_cwd(*, cwd: Path, directory: Path, payload: dict[str, Any]) -> bool:
    patterns = rule_paths(payload)
    if not patterns:
        return True
    relative_cwd = relative_cwd_path(cwd, directory)
    for pattern in patterns:
        normalized = str(pattern or "").strip().strip("\"'")
        if not normalized:
            continue
        normalized = normalized.lstrip("/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.endswith("/"):
            normalized = f"{normalized}**"
        if fnmatch.fnmatch(relative_cwd, normalized):
            return True
    return False


def discover_rule_docs(*, cwd: Path, directory: Path, safe_resolve: Callable[[Path], Path]) -> list[Path]:
    rule_root = directory / ".agenthub" / "rules"
    if not rule_root.is_dir():
        return []
    try:
        candidates = sorted(rule_root.glob("*.md"))
    except OSError:
        return []
    selected: list[tuple[int, Path]] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        payload = parse_rule_frontmatter(text)
        if not rule_enabled(payload):
            continue
        if not rule_matches_cwd(cwd=cwd, directory=directory, payload=payload):
            continue
        selected.append((rule_priority(payload), safe_resolve(path)))
    selected.sort(key=lambda item: (item[0], str(item[1])))
    return [path for _, path in selected]
