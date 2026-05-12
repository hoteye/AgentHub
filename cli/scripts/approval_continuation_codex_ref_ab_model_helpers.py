from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    elapsed_seconds: float
    timed_out: bool
    stdout_path: str
    stderr_path: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _file_state(workspace: Path, relative_path: str) -> dict[str, Any]:
    path = workspace / relative_path
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "content": "",
    }
    if path.exists() and path.is_file():
        payload["content"] = path.read_text(encoding="utf-8").strip()
    return payload
