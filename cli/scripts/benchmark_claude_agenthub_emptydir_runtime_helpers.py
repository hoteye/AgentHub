from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import apply_provider_home_override_env
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import apply_provider_home_override_env  # type: ignore[no-redef]

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import BenchmarkTask, ValidationSpec
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import BenchmarkTask, ValidationSpec  # type: ignore[no-redef]

_IGNORED_WORKSPACE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
}
_CLEARED_AGENTHUB_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "AGENT_CLI_API_KEY",
    "AGENT_CLI_BASE_URL",
    "AGENT_CLI_PROVIDER",
    "AGENT_CLI_MODEL",
    "AGENT_CLI_REASONING_EFFORT",
)

@dataclass
class CommandResult:
    name: str
    command: list[str]
    cwd: str
    exit_code: int
    elapsed_seconds: float
    timed_out: bool
    stdout_path: str
    stderr_path: str

class TimelineLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **payload: Any) -> None:
        entry = {
            "ts": datetime.now().astimezone().isoformat(),
            "event": str(event),
        }
        entry.update(payload)
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def _workspace_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _IGNORED_WORKSPACE_PARTS for part in rel.parts):
            continue
        files.append(rel.as_posix())
    return files

def _write_workspace_tree(root: Path, destination: Path) -> list[str]:
    files = _workspace_files(root)
    lines = [f"{item}\n" for item in files] if files else ["<empty>\n"]
    _write_text(destination, "".join(lines))
    return files

def _coerce_timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)

def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    logger: TimelineLogger | None = None,
    event_context: dict[str, Any] | None = None,
) -> CommandResult:
    start = time.perf_counter()
    timed_out = False
    stdout_text = ""
    stderr_text = ""
    exit_code = 0
    context = dict(event_context or {})
    if logger is not None:
        logger.emit(
            "command.started",
            name=name,
            cwd=str(cwd),
            command=list(command),
            command_shell=shlex.join(command),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            timeout_seconds=int(timeout_seconds),
            **context,
        )
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = int(completed.returncode)
        stdout_text = completed.stdout
        stderr_text = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_text = _coerce_timeout_text(exc.stdout)
        stderr_text = _coerce_timeout_text(exc.stderr)
    elapsed = round(time.perf_counter() - start, 3)
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    if logger is not None:
        logger.emit(
            "command.completed",
            name=name,
            cwd=str(cwd),
            command=list(command),
            command_shell=shlex.join(command),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            timeout_seconds=int(timeout_seconds),
            exit_code=int(exit_code),
            timed_out=bool(timed_out),
            elapsed_seconds=elapsed,
            **context,
        )
    return CommandResult(
        name=name,
        command=list(command),
        cwd=str(cwd),
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )

def _run_validation(
    *,
    validation: ValidationSpec,
    cwd: Path,
    env: dict[str, str],
    out_dir: Path,
    timeout_seconds: int,
    logger: TimelineLogger | None = None,
    event_context: dict[str, Any] | None = None,
) -> CommandResult:
    context = dict(event_context or {})
    if logger is not None:
        logger.emit(
            "validation.started",
            validation_name=validation.name,
            validation_command=validation.command,
            cwd=str(cwd),
            timeout_seconds=int(timeout_seconds),
            **context,
        )
    result = _run_command(
        name=validation.name,
        command=["/bin/bash", "-lc", validation.command],
        cwd=cwd,
        env=env,
        stdout_path=out_dir / f"{validation.name}.stdout.log",
        stderr_path=out_dir / f"{validation.name}.stderr.log",
        timeout_seconds=timeout_seconds,
        logger=logger,
        event_context={
            **context,
            "validation_name": validation.name,
            "validation_command": validation.command,
        },
    )
    if logger is not None:
        logger.emit(
            "validation.completed",
            validation_name=validation.name,
            validation_command=validation.command,
            cwd=str(cwd),
            exit_code=int(result.exit_code),
            timed_out=bool(result.timed_out),
            elapsed_seconds=float(result.elapsed_seconds),
            stdout_path=result.stdout_path,
            stderr_path=result.stderr_path,
            **context,
        )
    return result

def _build_claude_command(*, prompt: str, args: argparse.Namespace) -> list[str]:
    return [
        str(args.claude_bin),
        "-p",
        "--output-format",
        "json",
        "--model",
        str(args.claude_model),
        "--permission-mode",
        str(args.claude_permission_mode),
        prompt,
    ]

def _build_agenthub_command(*, prompt: str, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(Path(args.agenthub_main).resolve()),
        "--headless",
        "--json",
        "--approval-policy",
        "never",
        "--sandbox-mode",
        "danger-full-access",
        "--web-search-mode",
        "disabled",
        "--prompt",
        prompt,
    ]

def _build_claude_env() -> dict[str, str]:
    return dict(os.environ)

def _build_agenthub_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    for key in _CLEARED_AGENTHUB_ENV_KEYS:
        env.pop(key, None)
    env["AGENT_CLI_PROVIDER"] = str(args.agenthub_provider)
    env["AGENT_CLI_MODEL"] = str(args.agenthub_model)
    return apply_provider_home_override_env(env, provider_home=args.agenthub_provider_home)

def _missing_expected_files(task: BenchmarkTask, files: list[str]) -> list[str]:
    existing = set(files)
    return [path for path in task.expected_files if path not in existing]

def _validation_passed(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    for row in rows:
        if int(row.get("exit_code", 1)) != 0:
            return False
        if bool(row.get("timed_out")):
            return False
    return True

def _task_paths(root: Path, task: BenchmarkTask) -> dict[str, Path]:
    task_root = root / task.task_id
    return {
        "task_root": task_root,
        "prompt_path": task_root / "prompt.txt",
        "agenthub_root": task_root / "agenthub",
        "agenthub_workspace": task_root / "agenthub" / "workspace",
        "claude_root": task_root / "claude",
        "claude_workspace": task_root / "claude" / "workspace",
    }

def _ensure_task_layout(root: Path, task: BenchmarkTask) -> dict[str, Path]:
    paths = _task_paths(root, task)
    paths["agenthub_workspace"].mkdir(parents=True, exist_ok=True)
    paths["claude_workspace"].mkdir(parents=True, exist_ok=True)
    _write_text(paths["prompt_path"], task.prompt + "\n")
    return paths
