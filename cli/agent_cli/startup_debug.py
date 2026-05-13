from __future__ import annotations

import atexit
import faulthandler
import os
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TextIO

_STARTUP_DEBUG_STREAM: TextIO | None = None
_EXIT_LOG_INSTALLED = False


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def startup_debug_log_path() -> Path:
    configured = str(os.environ.get("AGENTHUB_START_DEBUG_LOG") or "").strip()
    if configured and configured not in {"stderr", "1"}:
        return Path(configured)
    return Path("/tmp/agenthub-start-debug.log")


def startup_debug_stream() -> TextIO | None:
    global _STARTUP_DEBUG_STREAM
    configured = str(os.environ.get("AGENTHUB_START_DEBUG_LOG") or "").strip()
    if configured in {"stderr", "1"}:
        return sys.stderr
    if _STARTUP_DEBUG_STREAM is not None and not _STARTUP_DEBUG_STREAM.closed:
        return _STARTUP_DEBUG_STREAM
    try:
        path = startup_debug_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _STARTUP_DEBUG_STREAM = path.open("a", encoding="utf-8", buffering=1)
    except Exception:
        _STARTUP_DEBUG_STREAM = None
    return _STARTUP_DEBUG_STREAM


def startup_log(message: str) -> None:
    stream = startup_debug_stream()
    if stream is None:
        return
    try:
        print(
            f"{_timestamp()} [DEBUG] [STARTUP] pid={os.getpid()} {message}", file=stream, flush=True
        )
    except Exception:
        return


def startup_profile_enabled() -> bool:
    configured = str(os.environ.get("AGENTHUB_START_DEBUG_LOG") or "").strip()
    explicit = str(os.environ.get("AGENTHUB_START_PROFILE") or "").strip().lower()
    return bool(configured) or explicit in {"1", "true", "yes", "on"}


def startup_profile_log(message: str) -> None:
    if startup_profile_enabled():
        startup_log(message)


@contextmanager
def startup_timer(label: str) -> Iterator[None]:
    if not startup_profile_enabled():
        yield
        return
    started_at = perf_counter()
    startup_log(f"profile.{label}.begin")
    try:
        yield
    except Exception as exc:
        elapsed_ms = (perf_counter() - started_at) * 1000
        startup_log(f"profile.{label}.error elapsed_ms={elapsed_ms:.1f} error={exc!r}")
        raise
    else:
        elapsed_ms = (perf_counter() - started_at) * 1000
        startup_log(f"profile.{label}.end elapsed_ms={elapsed_ms:.1f}")


def enable_startup_faulthandler() -> None:
    stream = startup_debug_stream()
    if stream is None:
        return
    try:
        faulthandler.enable(file=stream, all_threads=True)
    except Exception:
        return


def ignore_terminal_stop_signals() -> None:
    for name in ("SIGTSTP", "SIGTTIN", "SIGTTOU"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            signal.signal(signum, signal.SIG_IGN)
        except Exception:
            continue


def install_startup_exit_logging() -> None:
    global _EXIT_LOG_INSTALLED
    if _EXIT_LOG_INSTALLED:
        return
    _EXIT_LOG_INSTALLED = True

    def _log_exit() -> None:
        startup_log("process.atexit")

    try:
        atexit.register(_log_exit)
    except Exception:
        return
