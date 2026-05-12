from __future__ import annotations

import sys
from pathlib import Path

from cli.agent_cli.runtime_paths import ensure_runtime_project_root_env


def _configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            continue


def _ensure_repo_root_on_path() -> None:
    runtime_root = ensure_runtime_project_root_env()
    package_dir = Path(__file__).resolve().parent
    cli_root = str(package_dir.parent)
    repo_root = str(runtime_root)
    for candidate in (cli_root, repo_root):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
