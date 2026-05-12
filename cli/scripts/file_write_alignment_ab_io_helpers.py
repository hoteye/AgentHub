from __future__ import annotations

import json
import select
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _copy_workspace_files(workspace: Path, files: tuple[tuple[str, str], ...]) -> None:
    for rel_path, content in files:
        path = workspace / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _normalized_file_content(path: Path) -> str:
    return path.read_text(encoding="utf-8").rstrip("\n")


def _collect_expected_file_results(
    workspace: Path,
    expected_files: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rel_path, expected in expected_files:
        path = workspace / rel_path
        exists = path.exists()
        actual = _normalized_file_content(path) if exists else ""
        results.append(
            {
                "path": rel_path,
                "exists": exists,
                "expected": expected,
                "actual": actual,
                "ok": exists and actual == expected,
            }
        )
    return results


def _wait_for_json_line(stream: Any, timeout_s: int) -> dict[str, Any]:
    if stream is None:
        raise RuntimeError("missing serve stdout pipe")
    deadline = time.time() + max(timeout_s, 1)
    buffer = ""
    while time.time() < deadline:
        remaining = max(deadline - time.time(), 0.1)
        ready, _, _ = select.select([stream], [], [], min(remaining, 1.0))
        if not ready:
            continue
        chunk = stream.readline()
        if not chunk:
            raise RuntimeError("serve stdout closed before response")
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            stripped = line.strip()
            if not stripped:
                continue
            return json.loads(stripped)
    raise TimeoutError(f"timed out waiting for serve response after {timeout_s}s")
