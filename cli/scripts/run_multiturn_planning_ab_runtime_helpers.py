from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import (
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        resolve_codex_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        resolve_codex_source_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
CODEX_BIN = CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _prepare_codex_home(target_home: Path, workspace: Path) -> None:
    target_home.mkdir(parents=True, exist_ok=True)
    source_paths = resolve_codex_source_paths()
    config_text = source_paths.config_path.read_text(encoding="utf-8")
    config_text += f'\n[projects."{workspace}"]\ntrust_level = "trusted"\n'
    _write_text(target_home / "config.toml", config_text)
    shutil.copy(source_paths.auth_path, target_home / "auth.json")
    if source_paths.skills_dir.exists() and not (target_home / "skills").exists():
        os.symlink(source_paths.skills_dir, target_home / "skills")


def _inventory(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.exists():
        return items
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        items.append({"path": str(path.relative_to(root)), "size": path.stat().st_size})
    return items


def _codex_exec_command(
    *,
    prompt: str,
    turn_dir: Path,
    resume: bool,
) -> list[str]:
    last_message_path = turn_dir / "last_message.txt"
    base = [str(CODEX_BIN), "exec"]
    if resume:
        base.extend(["resume", "--last"])
    base.extend(
        [
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o",
            str(last_message_path),
            "--skip-git-repo-check",
            prompt,
        ]
    )
    return base
