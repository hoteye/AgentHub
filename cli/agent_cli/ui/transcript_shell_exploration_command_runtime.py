from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Callable, TypeVar

from cli.agent_cli.ui import transcript_shell_exploration_command_helpers_runtime

SummaryT = TypeVar("SummaryT")


def unwrap_shell_wrapped_command(command_text: str) -> str:
    command = str(command_text or "").strip()
    if not command:
        return ""
    match = re.match(r"^(?P<shell>\S+)\s+(?P<flag>-lc|-c)\s+(?P<script>\"(?:\\.|[^\"])*\")\s*$", command, re.DOTALL)
    if match and Path(str(match.group("shell") or "")).name in {"bash", "sh", "zsh"}:
        try:
            return str(json.loads(str(match.group("script") or "")) or "").strip()
        except json.JSONDecodeError:
            pass
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        argv = []
    if len(argv) == 3 and argv[1] in {"-lc", "-c"}:
        shell_name = Path(argv[0]).name
        if shell_name in {"bash", "sh", "zsh"}:
            return str(argv[2] or "").strip()
    return command


def strip_leading_shell_comment_label(command_text: str) -> str:
    lines = str(command_text or "").splitlines()
    for index, raw_line in enumerate(lines):
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("#") and not line.startswith("#!"):
            remaining = lines[:index] + lines[index + 1 :]
            return "\n".join(remaining).strip()
        break
    return str(command_text or "").strip()


def command_execution_exploration_summaries(
    item: dict[str, object],
    *,
    build_summary_fn: Callable[..., SummaryT],
) -> list[SummaryT] | None:
    command_text = strip_leading_shell_comment_label(
        unwrap_shell_wrapped_command(str(item.get("command") or "").strip())
    )
    if not command_text:
        return None
    segments = transcript_shell_exploration_command_helpers_runtime.split_shell_command_segments(command_text)
    if segments is None:
        return None
    cwd: str | None = None
    stream_subject: str | None = None
    summaries: list[SummaryT] = []
    for tokens in segments:
        if not tokens:
            continue
        if tokens[0] == "cd":
            target = transcript_shell_exploration_command_helpers_runtime.cd_target(tokens[1:])
            if target is None:
                return None
            cwd = transcript_shell_exploration_command_helpers_runtime.join_display_paths(cwd, target) if cwd else target
            continue
        parsed = transcript_shell_exploration_command_helpers_runtime.parse_shell_segment(
            tokens,
            cwd=cwd,
            build_summary_fn=build_summary_fn,
        )
        parsed = transcript_shell_exploration_command_helpers_runtime.bind_stream_subject(
            parsed,
            stream_subject=stream_subject,
            build_summary_fn=build_summary_fn,
        )
        if parsed is not None:
            if not summaries or summaries[-1] != parsed:
                summaries.append(parsed)
            if stream_subject:
                stream_subject = None
            continue
        source_subject = transcript_shell_exploration_command_helpers_runtime.pipeline_source_subject(tokens)
        if source_subject:
            stream_subject = source_subject
            continue
        stream_read = transcript_shell_exploration_command_helpers_runtime.stream_read_summary(
            tokens,
            stream_subject=stream_subject,
            build_summary_fn=build_summary_fn,
        )
        if stream_read is not None:
            if not summaries or summaries[-1] != stream_read:
                summaries.append(stream_read)
            stream_subject = None
            continue
        if transcript_shell_exploration_command_helpers_runtime.is_small_formatting_command(tokens):
            continue
        if (
            len(segments) > 1
            and transcript_shell_exploration_command_helpers_runtime.is_skippable_banner_command(tokens)
        ):
            continue
        return None
    return summaries or None
