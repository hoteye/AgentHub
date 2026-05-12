from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable, Iterable, List, Optional

# Map rg --type names to glob suffixes for the Python fallback
_TYPE_GLOB: dict[str, str] = {
    "py": "*.py", "js": "*.js", "ts": "*.ts", "jsx": "*.jsx", "tsx": "*.tsx",
    "rust": "*.rs", "go": "*.go", "java": "*.java", "c": "*.c",
    "cpp": "*.cpp", "cs": "*.cs", "rb": "*.rb", "sh": "*.sh",
    "html": "*.html", "css": "*.css", "json": "*.json", "yaml": "*.yaml",
    "toml": "*.toml", "md": "*.md", "txt": "*.txt",
}

def iter_files(base_path: Path) -> Iterable[Path]:
    if base_path.is_file():
        yield base_path
        return
    for path in sorted(base_path.rglob("*")):
        if path.is_file():
            yield path


def normalize_rel_path(path_text: str) -> str:
    text = str(path_text or "").strip()
    if text.startswith("./"):
        text = text[2:]
    return text or "."


def normalize_query_text(query: str) -> str:
    text = str(query or "").strip()
    if not text:
        return ""
    text = text.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    return re.sub(r"\s+", " ", text).strip()


def query_arg_for_target(target: Path, workspace_root: Path, *, relative_text_fn: Callable[[Path, Path], str]) -> str:
    if target == workspace_root:
        return "."
    return relative_text_fn(target, workspace_root)


def normalize_rg_path(raw_path: str, *, workspace_root: Path) -> str:
    raw = str(raw_path or "").strip()
    if not raw:
        return ""
    if Path(raw).is_absolute():
        try:
            normalized = str(Path(raw).resolve().relative_to(workspace_root)).replace("\\", "/")
        except ValueError:
            normalized = str(Path(raw).resolve()).replace("\\", "/")
    else:
        normalized = normalize_rel_path(raw).replace("\\", "/")
    return normalized


def collect_rg_paths(*, output: str, workspace_root: Path, limit: int) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw_line in str(output or "").splitlines():
        normalized = normalize_rg_path(raw_line, workspace_root=workspace_root)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
        if len(paths) >= int(limit):
            break
    return paths


def python_grep_files(
    *,
    workspace_root: Path,
    target: Path,
    pattern: str,
    include: str | None,
    limit: int,
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    line_numbers: bool = False,
    after_context: Optional[int] = None,
    before_context: Optional[int] = None,
    context: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
) -> list[str]:
    flags = 0
    if case_insensitive:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.DOTALL
    try:
        regex = re.compile(str(pattern), flags)
    except re.error as exc:
        raise file_tool_error_cls(f"invalid regex pattern: {exc}") from exc

    # Resolve effective include glob: file_type takes precedence over include
    effective_include = str(include or "").strip() or None
    if file_type:
        type_glob = _TYPE_GLOB.get(str(file_type).lower())
        if type_glob:
            effective_include = type_glob

    ctx_after = int(context if context is not None else (after_context or 0))
    ctx_before = int(context if context is not None else (before_context or 0))

    candidates: list[tuple[float, Path, str]] = []
    for item in iter_files(target):
        rel_path = relative_text_fn(item, workspace_root).replace("\\", "/")
        if effective_include and not Path(rel_path).match(effective_include):
            continue
        try:
            text = item.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not regex.search(text):
            continue
        try:
            sort_key = float(item.stat().st_mtime)
        except OSError:
            sort_key = 0.0
        candidates.append((sort_key, item, rel_path))

    candidates.sort(key=lambda x: (-x[0], x[2]))

    if output_mode == "files_with_matches":
        ordered: list[str] = []
        seen: set[str] = set()
        for _, _, rel_path in candidates:
            if rel_path in seen:
                continue
            seen.add(rel_path)
            ordered.append(rel_path)
            if len(ordered) >= int(limit):
                break
        return ordered[offset:] if offset else ordered

    if output_mode == "count":
        lines: list[str] = []
        for _, item, rel_path in candidates:
            try:
                text = item.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            count = len(regex.findall(text))
            if count:
                lines.append(f"{rel_path}:{count}")
        lines = lines[offset:] if offset else lines
        return lines[:limit] if limit else lines

    # content mode
    output_lines: list[str] = []
    for _, item, rel_path in candidates:
        try:
            file_lines = item.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(file_lines, start=1):
            if not regex.search(line):
                continue
            if ctx_before or ctx_after:
                start = max(0, lineno - 1 - ctx_before)
                end = min(len(file_lines), lineno + ctx_after)
                for i in range(start, end):
                    prefix = f"{rel_path}:{i + 1}:" if line_numbers else f"{rel_path}:"
                    output_lines.append(f"{prefix}{file_lines[i]}")
                output_lines.append("--")
            else:
                prefix = f"{rel_path}:{lineno}:" if line_numbers else f"{rel_path}:"
                output_lines.append(f"{prefix}{line}")
        if len(output_lines) >= limit + offset:
            break
    output_lines = output_lines[offset:] if offset else output_lines
    return output_lines[:limit] if limit else output_lines


def build_file_search_payload(
    *,
    root: Path,
    grep_payload: dict[str, Any],
    normalized_query: str,
) -> dict[str, Any]:
    paths = [str(item).strip() for item in grep_payload.get("paths") or [] if str(item).strip()]
    return {
        "ok": bool(paths),
        "result_success": bool(paths),
        "workspace_root": str(root),
        "path": str(grep_payload.get("path") or "."),
        "query": normalized_query,
        "count": len(paths),
        "file_count": len(paths),
        "matches": [{"path": item} for item in paths],
        "text": str(grep_payload.get("text") or ""),
        "engine": "compat:grep_files",
        "compatibility_alias": "grep_files",
    }
