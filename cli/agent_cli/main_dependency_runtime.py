from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Sequence
from typing import TextIO


def _argv_requests_help(argv: Sequence[str] | None) -> bool:
    return any(str(item or "").strip() in {"--help", "-h"} for item in list(argv or []))


def _has_mcp_serve_request(argv: Sequence[str] | None) -> bool:
    if argv is None:
        return False
    args = [str(item or "").strip() for item in list(argv)]
    return len(args) >= 2 and args[0] == "mcp" and args[1] == "serve"


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


def _git_install_hint() -> str:
    return "\n".join(
        [
            "AgentHub requires git, but git was not found in PATH.",
            "Install git and run AgentHub again.",
            "",
            "Ubuntu/Debian: sudo apt install git",
            "Fedora: sudo dnf install git",
            "Arch: sudo pacman -S git",
            "macOS: brew install git",
        ]
    )


def _ensure_git_dependency(*, stderr: TextIO | None = None) -> bool:
    if shutil.which("git"):
        return True
    print(_git_install_hint(), file=stderr or sys.stderr)
    return False


def _tmux_preview_supported_on_host() -> bool:
    return sys.platform != "win32"


def _tmux_install_hint() -> str:
    return "\n".join(
        [
            "AgentHub file/URL preview panes need tmux, but tmux was not found in PATH.",
            "Install tmux to enable the preview pane. Continuing without the preview pane.",
            "",
            "Ubuntu/Debian: sudo apt install tmux",
            "Fedora: sudo dnf install tmux",
            "Arch: sudo pacman -S tmux",
            "macOS: brew install tmux",
        ]
    )


def _warn_missing_tmux_dependency_for_tui(
    argv: Sequence[str],
    *,
    headless: bool,
    stderr: TextIO | None = None,
) -> None:
    if not bool(getattr(sys, "frozen", False)):
        return
    if _argv_requests_help(argv):
        return
    if not _tmux_preview_supported_on_host():
        return
    if str(shutil.which("tmux") or "").strip():
        return
    if str(os.environ.get("AGENTHUB_TMUX_DEPENDENCY_CHECKED") or "").strip():
        return
    if headless:
        return
    print(_tmux_install_hint(), file=stderr or sys.stderr)
