from __future__ import annotations

import os
from pathlib import Path
from shutil import copy2

from cli.agent_cli.runtime_paths import (
    LEGACY_PROJECT_LOCAL_DATA_DIRNAMES,
    PROJECT_LOCAL_DATA_DIRNAME,
    PROJECT_ROOT_ENV,
    is_frozen_runtime,
    project_local_data_dir,
)

_GATEWAY_JSONL_FILENAMES = {
    "events": "events.jsonl",
    "workflow_runs": "workflow_runs.jsonl",
    "action_requests": "action_requests.jsonl",
    "approval_tickets": "approval_tickets.jsonl",
    "audit_records": "audit_records.jsonl",
}


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _default_gateway_project_root() -> Path:
    configured = str(os.environ.get(PROJECT_ROOT_ENV) or "").strip()
    if configured:
        return _safe_resolve(Path(configured))
    return _safe_resolve(Path(__file__).resolve().parents[2])


def _default_gateway_base_dir(*, root: Path | None = None) -> Path:
    if root is None and is_frozen_runtime():
        return project_local_data_dir() / "gateway"
    project_root = _safe_resolve(root or _default_gateway_project_root())
    return project_root / PROJECT_LOCAL_DATA_DIRNAME / "gateway"


def _legacy_gateway_base_dirs(*, root: Path | None = None) -> list[Path]:
    project_root = _safe_resolve(root or _default_gateway_project_root())
    return [project_root / dirname / "gateway" for dirname in LEGACY_PROJECT_LOCAL_DATA_DIRNAMES]


def _migrate_legacy_gateway_state(preferred_dir: Path, *, root: Path | None = None) -> None:
    preferred_dir.mkdir(parents=True, exist_ok=True)
    for legacy_dir in _legacy_gateway_base_dirs(root=root):
        if not legacy_dir.exists() or legacy_dir == preferred_dir:
            continue
        for filename in _GATEWAY_JSONL_FILENAMES.values():
            source = legacy_dir / filename
            target = preferred_dir / filename
            if not source.exists() or target.exists():
                continue
            copy2(source, target)
