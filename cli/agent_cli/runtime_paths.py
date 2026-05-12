from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT_ENV = "AGENTHUB_PROJECT_ROOT"
AGENT_CLI_HOME_ENV = "AGENT_CLI_HOME"
DEFAULT_AGENT_CLI_HOME_DIRNAME = ".agent_cli"
PROJECT_LOCAL_DATA_DIRNAME = ".config"
LEGACY_PROJECT_LOCAL_DATA_DIRNAMES = (".agent_cli", ".agent_cli_legacy")
PROJECT_LOCAL_DATA_DIR_CANDIDATES = (
    PROJECT_LOCAL_DATA_DIRNAME,
    *LEGACY_PROJECT_LOCAL_DATA_DIRNAMES,
)


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_frozen_runtime() -> bool:
    return _is_frozen_runtime()


def agent_cli_home() -> Path:
    configured = str(os.environ.get(AGENT_CLI_HOME_ENV) or "").strip()
    if configured:
        return _safe_resolve(Path(configured))
    try:
        home = Path.home()
    except RuntimeError:
        fallback_home = str(os.environ.get("HOME") or "").strip()
        if fallback_home:
            home = Path(fallback_home)
        else:
            raise
    return _safe_resolve(home / DEFAULT_AGENT_CLI_HOME_DIRNAME)


def runtime_project_root() -> Path:
    configured = str(os.environ.get(PROJECT_ROOT_ENV) or "").strip()
    if configured:
        return _safe_resolve(Path(configured))
    if _is_frozen_runtime():
        return _safe_resolve(Path(sys.executable).parent)
    return _safe_resolve(Path(__file__).resolve().parents[2])


def ensure_runtime_project_root_env() -> Path:
    root = runtime_project_root()
    os.environ.setdefault(PROJECT_ROOT_ENV, str(root))
    return root


def project_local_data_dir(*, root: Path | None = None) -> Path:
    if root is None and _is_frozen_runtime():
        return agent_cli_home()
    base = _safe_resolve(root or runtime_project_root())
    preferred = base / PROJECT_LOCAL_DATA_DIRNAME
    if preferred.exists():
        return preferred
    for dirname in LEGACY_PROJECT_LOCAL_DATA_DIRNAMES:
        candidate = base / dirname
        if candidate.exists():
            return candidate
    return preferred
