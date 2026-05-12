from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.command_execution_wave03_ab_model_helpers import CommandResult, _now_iso, _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from command_execution_wave03_ab_model_helpers import CommandResult, _now_iso, _write_text  # type: ignore[no-redef]


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    dry_run: bool,
) -> CommandResult:
    started_at = _now_iso()
    if dry_run:
        _write_text(stdout_path, "")
        _write_text(stderr_path, "")
        return CommandResult(
            name=name,
            command=list(command),
            cwd=str(cwd),
            exit_code=0,
            elapsed_seconds=0.0,
            timed_out=False,
            started_at=started_at,
            ended_at=started_at,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
        )
    start = time.perf_counter()
    timed_out = False
    stdout_text = ""
    stderr_text = ""
    exit_code = 0
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
    ended_at = _now_iso()
    elapsed = round(time.perf_counter() - start, 3)
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    return CommandResult(
        name=name,
        command=list(command),
        cwd=str(cwd),
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        started_at=started_at,
        ended_at=ended_at,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _parse_agenthub_output(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "commentary_text": "",
        "tool_event_count": 0,
        "tool_names": [],
        "turn_event_count": 0,
        "response_item_count": 0,
        "status": {},
    }
    if not stdout_path.exists():
        return payload
    text = stdout_path.read_text(encoding="utf-8").strip()
    if not text:
        return payload
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        payload["parse_error"] = text[:400]
        return payload
    tool_events = [item for item in list(data.get("tool_events") or []) if isinstance(item, dict)]
    payload["assistant_text"] = str(data.get("assistant_text") or "")
    payload["commentary_text"] = str(data.get("commentary_text") or "")
    payload["tool_event_count"] = len(tool_events)
    payload["tool_names"] = [str(item.get("name") or "") for item in tool_events]
    payload["turn_event_count"] = len(list(data.get("turn_events") or []))
    payload["response_item_count"] = len(list(data.get("response_items") or []))
    payload["status"] = dict(data.get("status") or {})
    return payload


def _parse_codex_output(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "thread_id": "",
        "item_counts": {},
        "completed_item_counts": {},
        "errors": [],
    }
    if not stdout_path.exists():
        return payload
    item_counts: dict[str, int] = {}
    completed_item_counts: dict[str, int] = {}
    agent_messages: list[str] = []
    for raw_line in stdout_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type == "thread.started":
            payload["thread_id"] = str(event.get("thread_id") or payload["thread_id"])
        if event_type == "error":
            message = str(event.get("message") or "").strip()
            if message:
                payload["errors"].append(message)
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
            if event_type == "item.completed":
                completed_item_counts[item_type] = completed_item_counts.get(item_type, 0) + 1
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                agent_messages.append(text)
    payload["assistant_text"] = agent_messages[-1] if agent_messages else ""
    payload["item_counts"] = item_counts
    payload["completed_item_counts"] = completed_item_counts
    return payload


def _build_agenthub_command(*, prompt: str, main_path: Path) -> list[str]:
    return [
        sys.executable,
        str(main_path),
        "--headless",
        "--json",
        "--approval-policy",
        "never",
        "--sandbox-mode",
        "danger-full-access",
        "--prompt",
        prompt,
    ]


def _build_codex_command(*, prompt: str, workspace: Path, model: str, reasoning_effort: str) -> list[str]:
    command = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(workspace),
        "-m",
        model,
    ]
    normalized_effort = str(reasoning_effort or "").strip()
    if normalized_effort:
        command.extend(["-c", f'model_reasoning_effort="{normalized_effort}"'])
    command.append(prompt)
    return command
