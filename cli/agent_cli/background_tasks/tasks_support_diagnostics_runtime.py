from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


def find_git_root(path: Path) -> Path | None:
    current = path
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def capture_command_output(command: list[str], *, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    return str(completed.stdout or "")


def git_repo_state(git_root: Path, *, warnings: list[str]) -> dict[str, Any] | None:
    git_executable = shutil.which("git")
    if not git_executable:
        warnings.append("git executable not available; repo_state skipped")
        return None
    porcelain = capture_command_output([git_executable, "status", "--porcelain", "--untracked-files=all"], cwd=git_root)
    if porcelain is None:
        warnings.append("git status unavailable; repo_state skipped")
        return None
    status_lines = [line for line in porcelain.splitlines() if line.strip()]
    repo_state: dict[str, Any] = {
        "dirty": bool(status_lines),
        "changed_file_count": len([line for line in status_lines if not line.startswith("?? ")]),
        "untracked_file_count": len([line for line in status_lines if line.startswith("?? ")]),
    }
    tracked = capture_command_output([git_executable, "ls-files"], cwd=git_root)
    if tracked is None:
        warnings.append("git ls-files unavailable; tracked_file_count skipped")
    else:
        repo_state["tracked_file_count"] = len([line for line in tracked.splitlines() if line.strip()])
    return repo_state


def collect_bootstrap_diagnostics(
    cwd: Path,
    *,
    bootstrap_dependency_files: tuple[str, ...],
    relative_task_path_fn: Callable[[Path, Any], str],
    dedupe_compact_items_fn: Callable[[list[str]], list[str]],
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "cwd": str(cwd),
        "cwd_exists": cwd.exists(),
        "is_dir": cwd.is_dir() if cwd.exists() else False,
        "git_root_detected": False,
        "git_root": "",
        "git_dir_present": False,
        "dependency_files": [],
        "bootstrap_warnings": [],
        "bootstrap_error_category": "",
    }
    if not diagnostics["cwd_exists"]:
        diagnostics["bootstrap_error_category"] = "cwd_missing"
        return diagnostics
    if not diagnostics["is_dir"]:
        diagnostics["bootstrap_error_category"] = "cwd_not_directory"
        return diagnostics
    git_root = find_git_root(cwd)
    warnings: list[str] = []
    if git_root is not None:
        diagnostics["git_root_detected"] = True
        diagnostics["git_root"] = str(git_root)
        diagnostics["git_dir_present"] = (git_root / ".git").exists()
        repo_state = git_repo_state(git_root, warnings=warnings)
        if isinstance(repo_state, dict) and repo_state:
            diagnostics["repo_state"] = repo_state
    dependency_files: list[str] = []
    search_roots = [cwd]
    if git_root is not None and git_root != cwd:
        search_roots.append(git_root)
    for search_root in search_roots:
        for filename in bootstrap_dependency_files:
            candidate = search_root / filename
            if candidate.exists():
                relative = relative_task_path_fn(cwd, candidate)
                dependency_files.append(relative or filename)
    diagnostics["dependency_files"] = dedupe_compact_items_fn(dependency_files[:16])
    if git_root is None:
        warnings.append("git root not detected")
    diagnostics["bootstrap_warnings"] = dedupe_compact_items_fn(warnings[:8])
    return diagnostics


def bootstrap_diagnostic_artifact_fields(diagnostics: dict[str, Any]) -> dict[str, Any]:
    artifact = {
        "bootstrap_diagnostics": dict(diagnostics or {}),
        "cwd_exists": bool(diagnostics.get("cwd_exists")),
        "is_dir": bool(diagnostics.get("is_dir")),
        "git_root_detected": bool(diagnostics.get("git_root_detected")),
        "git_dir_present": bool(diagnostics.get("git_dir_present")),
        "dependency_files": list(diagnostics.get("dependency_files") or []),
        "bootstrap_warnings": list(diagnostics.get("bootstrap_warnings") or []),
    }
    if str(diagnostics.get("git_root") or "").strip():
        artifact["git_root"] = str(diagnostics.get("git_root") or "").strip()
    if str(diagnostics.get("bootstrap_error_category") or "").strip():
        artifact["bootstrap_error_category"] = str(diagnostics.get("bootstrap_error_category") or "").strip()
    repo_state = diagnostics.get("repo_state")
    if isinstance(repo_state, dict) and repo_state:
        artifact["repo_state"] = dict(repo_state)
    return artifact


def bootstrap_failure_error(diagnostics: dict[str, Any]) -> str:
    category = str(diagnostics.get("bootstrap_error_category") or "").strip()
    cwd = str(diagnostics.get("cwd") or "").strip()
    if category == "cwd_missing":
        return f"workspace root does not exist: {cwd}"
    if category == "cwd_not_directory":
        return f"workspace root is not a directory: {cwd}"
    return f"workspace bootstrap failed: {cwd or '-'}"


def normalize_policy_path(base: Path, candidate: Any) -> str:
    text = str(candidate or "").strip().replace("\\", "/")
    if not text:
        return ""
    if text in {".", "./"}:
        return "."
    path = Path(text).expanduser()
    if path.is_absolute():
        try:
            return path.resolve().relative_to(base.resolve()).as_posix() or "."
        except (OSError, RuntimeError, ValueError):
            return path.as_posix()
    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or "."


def path_matches_rule(path_text: str, rule: str) -> bool:
    normalized_path = str(path_text or "").strip().strip("/")
    normalized_rule = str(rule or "").strip().strip("/")
    if not normalized_rule or normalized_rule == ".":
        return True
    return normalized_path == normalized_rule or normalized_path.startswith(f"{normalized_rule}/")


def paths_outside_policy(
    paths: list[str],
    *,
    allowed_paths: list[str],
    blocked_paths: list[str],
    dedupe_compact_items_fn: Callable[[list[str]], list[str]],
) -> list[str]:
    violations: list[str] = []
    for path_text in paths:
        normalized = str(path_text or "").strip().strip("/")
        if not normalized:
            continue
        if any(path_matches_rule(normalized, rule) for rule in blocked_paths):
            violations.append(normalized)
            continue
        if allowed_paths and not any(path_matches_rule(normalized, rule) for rule in allowed_paths):
            violations.append(normalized)
    return dedupe_compact_items_fn(violations[:64])


def benchmark_success_summary(report_path: Path) -> str:
    if not report_path.exists():
        return "benchmark completed"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"benchmark completed: {report_path.name}"
    runs = list(payload.get("runs") or [])
    summary_rows = list(payload.get("summary") or [])
    if summary_rows:
        return f"benchmark completed: cases={len(summary_rows)} runs={len(runs)}"
    return "benchmark completed"


def smoke_success_summary(kind: str, report_path: Path) -> str:
    if not report_path.exists():
        return f"smoke completed: {kind}"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"smoke completed: {kind}"
    case_results = list(payload.get("cases") or payload.get("results") or [])
    if case_results:
        return f"smoke completed: {kind} cases={len(case_results)}"
    if isinstance(payload.get("summary"), list):
        return f"smoke completed: {kind} cases={len(list(payload.get('summary') or []))}"
    return f"smoke completed: {kind}"


def trim_error(text: str, *, max_chars: int = 280) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "..."


def decode_json_text(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(text or ""))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
