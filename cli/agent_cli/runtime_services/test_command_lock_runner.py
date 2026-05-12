from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TextIO

try:
    import fcntl
except ImportError:  # pragma: no cover - windows fallback
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - posix fallback
    msvcrt = None  # type: ignore[assignment]


def _acquire_lock(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    if msvcrt is not None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)


def _release_lock(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is not None:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command while holding a machine-global test lock")
    parser.add_argument("--lock-path", required=True, help="Path to the lock file")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command argv after --")
    args = parser.parse_args(argv)

    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("test lock runner requires a command after --", file=sys.stderr)
        return 2

    lock_path = Path(str(args.lock_path or "")).expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        _acquire_lock(handle)
        try:
            process = subprocess.Popen(command)
            return int(process.wait() or 0)
        finally:
            _release_lock(handle)


if __name__ == "__main__":
    raise SystemExit(main())
