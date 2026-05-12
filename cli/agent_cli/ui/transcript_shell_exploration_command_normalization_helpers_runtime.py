from __future__ import annotations

import re
import shlex
from pathlib import Path


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC_RE = re.compile(r"^\\\\[^\\\/]+[\\\/][^\\\/]+")


def split_shell_command_segments(command_text: str) -> list[list[str]] | None:
    normalized = str(command_text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ; ")
    lexer = shlex.shlex(normalized, posix=True, punctuation_chars="|&;()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    if not tokens:
        return []
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"|", "&&", "||", ";"}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def join_display_paths(base: str | None, rel: str) -> str:
    target = str(rel or "").strip()
    if not target:
        return str(base or "").strip()
    if _is_abs_like_path(target):
        return target
    base_text = str(base or "").strip()
    if not base_text:
        return target
    if target == ".":
        return base_text
    return str(Path(base_text) / target)


def cd_target(args: list[str]) -> str | None:
    if not args:
        return None
    target: str | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return args[index + 1] if index + 1 < len(args) else None
        if arg in {"-L", "-P"}:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        target = arg
        index += 1
    return target


def pipeline_source_subject(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    normalized = [str(token or "").strip() for token in tokens]
    if any(token == "--help" for token in normalized[1:]):
        return shlex.join([token for token in normalized if token])
    return None


def _short_display_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/")
    trimmed = normalized.rstrip("/")
    if not trimmed:
        return "."
    parts = [
        part
        for part in reversed(trimmed.split("/"))
        if part and part not in {"build", "dist", "node_modules", "src"}
    ]
    return parts[0] if parts else trimmed


def _is_abs_like_path(path: str) -> bool:
    text = str(path or "").strip()
    if not text:
        return False
    return Path(text).is_absolute() or bool(_WINDOWS_DRIVE_RE.match(text) or _WINDOWS_UNC_RE.match(text))
