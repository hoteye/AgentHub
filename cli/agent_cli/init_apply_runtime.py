from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.workspace_context import LOCAL_PROJECT_DOC_FILENAME


def apply_init_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(str(proposal.get("project_root") or "")).resolve()
    artifacts = [dict(item) for item in list(proposal.get("artifacts") or []) if isinstance(item, dict)]
    created_paths: list[str] = []
    updated_paths: list[str] = []
    skipped_paths: list[str] = []
    written_paths: list[str] = []
    local_selected = False

    for artifact in artifacts:
        path = Path(str(artifact.get("path") or "")).resolve()
        change_mode = str(artifact.get("change_mode") or "noop").strip() or "noop"
        content = str(artifact.get("content") or "")
        if artifact.get("kind") == "local_doc":
            local_selected = True
        if change_mode == "noop":
            skipped_paths.append(str(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(str(path))
        if change_mode in {"create", "split_rules"}:
            created_paths.append(str(path))
        else:
            updated_paths.append(str(path))

    gitignore_updated = False
    gitignore_path = None
    if local_selected and project_root:
        gitignore_path = project_root / ".gitignore"
        gitignore_updated = _ensure_gitignore_entry(gitignore_path, f"/{LOCAL_PROJECT_DOC_FILENAME}")

    return {
        "status": "applied",
        "project_root": str(project_root),
        "written_paths": written_paths,
        "created_paths": created_paths,
        "updated_paths": updated_paths,
        "skipped_paths": skipped_paths,
        "gitignore_updated": gitignore_updated,
        "gitignore_path": str(gitignore_path) if gitignore_path else "",
    }


def _ensure_gitignore_entry(path: Path, entry: str) -> bool:
    normalized_entry = str(entry or "").strip()
    if not normalized_entry:
        return False
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    lines = {str(line).strip() for line in existing.splitlines() if str(line).strip()}
    if normalized_entry in lines:
        return False
    prefix = existing.rstrip()
    next_text = f"{prefix}\n{normalized_entry}\n" if prefix else f"{normalized_entry}\n"
    path.write_text(next_text, encoding="utf-8")
    return True
