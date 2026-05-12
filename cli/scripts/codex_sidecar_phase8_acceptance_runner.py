from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.scripts.codex_sidecar_phase8_acceptance_report import (
    CheckResult,
    CheckStatus,
    _tail_lines,
)


def _run_check(name: str, fn: Callable[[], dict[str, Any] | None]) -> CheckResult:
    started = time.monotonic()
    try:
        details = fn() or {}
        return CheckResult(
            name=name,
            status="pass",
            duration_seconds=round(time.monotonic() - started, 3),
            details=details,
        )
    except Exception as exc:
        return CheckResult(
            name=name,
            status="fail",
            duration_seconds=round(time.monotonic() - started, 3),
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_subprocess_check(
    name: str,
    command: list[str],
    *,
    timeout: float,
    cwd: Path,
) -> CheckResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=name,
            status="fail",
            duration_seconds=round(time.monotonic() - started, 3),
            error=f"subprocess timed out after {timeout:.1f}s",
            command=command,
            stdout_tail=_tail_lines(exc.stdout or ""),
            stderr_tail=_tail_lines(exc.stderr or ""),
        )
    status: CheckStatus = "pass" if completed.returncode == 0 else "fail"
    return CheckResult(
        name=name,
        status=status,
        duration_seconds=round(time.monotonic() - started, 3),
        error="" if status == "pass" else f"subprocess exited with {completed.returncode}",
        command=command,
        stdout_tail=_tail_lines(completed.stdout),
        stderr_tail=_tail_lines(completed.stderr),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
