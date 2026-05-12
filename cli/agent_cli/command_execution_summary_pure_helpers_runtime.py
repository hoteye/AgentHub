from __future__ import annotations

import re
import shlex
from typing import Any

from cli.agent_cli.ui import transcript_shell_exploration_command_helpers_runtime
from cli.agent_cli.ui import transcript_shell_exploration_command_runtime


DEFAULT_COMMAND_DISPLAY_MAX_LINES = 2
DEFAULT_COMMAND_DISPLAY_MAX_CHARS = 160
_SHELL_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_REDIRECTION_TOKEN_RE = re.compile(r"^\d*(?:>>?|<<?|<>|>&|<&).*$")
_REDIRECTION_OPERATOR_TOKENS = {">", ">>", "<", "<<", "<>", ">&", "<&"}
_SETUP_ONLY_COMMANDS = {"export", "unset", "alias", "unalias", "source", ".", "set", "shopt", "trap", "umask"}


def shell_comment_label_from_command(command_text: str) -> str:
    command = transcript_shell_exploration_command_runtime.unwrap_shell_wrapped_command(
        str(command_text or "").strip()
    )
    if not command:
        return ""
    for raw_line in command.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if not line.startswith("#") or line.startswith("#!"):
            return ""
        return re.sub(r"^#+\s*", "", line).strip()
    return ""


def mapping_prefers_verbatim_command_display(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status in {"failed", "error"}:
        return True
    for key in ("returncode", "exit_code"):
        value = item.get(key)
        if value in {None, "", 0, "0"}:
            continue
        return True
    return bool(item.get("timed_out"))


def verbatim_command_display_source(command_text: str) -> str:
    command = transcript_shell_exploration_command_runtime.unwrap_shell_wrapped_command(
        str(command_text or "").strip()
    )
    if not command:
        return ""
    stripped = transcript_shell_exploration_command_runtime.strip_leading_shell_comment_label(command)
    return stripped or command


def compact_command_display_source(command_text: str) -> str:
    command = transcript_shell_exploration_command_runtime.strip_leading_shell_comment_label(str(command_text or "").strip())
    if not command:
        return ""
    segments, _ = _split_compound_command_display_parts(command)
    if not segments:
        tokens = _display_tokens_for_segment(command)
        return shlex.join(tokens) if tokens else command
    compound = len(segments) > 1
    if not compound:
        if "\n" in command:
            return command
        tokens = _display_tokens_for_segment(command)
        return shlex.join(tokens) if tokens else command
    rendered_segments: list[str] = []
    for segment in segments:
        if compound and _is_skippable_display_segment(segment):
            continue
        display_tokens = _display_tokens_for_segment(segment)
        if display_tokens:
            rendered_segments.append(shlex.join(display_tokens))
            continue
        segment_text = str(segment or "").strip()
        if segment_text:
            rendered_segments.append(segment_text)
    if rendered_segments:
        return " / ".join(rendered_segments)
    fallback_tokens = _display_tokens_for_segment(segments[-1] if segments else command)
    if fallback_tokens:
        return shlex.join(fallback_tokens)
    return command


def truncate_command_text(
    text: str,
    *,
    max_lines: int = DEFAULT_COMMAND_DISPLAY_MAX_LINES,
    max_chars: int = DEFAULT_COMMAND_DISPLAY_MAX_CHARS,
    single_line: bool = False,
) -> str:
    lines = [str(line or "").rstrip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return ""
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    rendered = " / ".join(lines) if single_line else "\n".join(lines)
    rendered = rendered.strip()
    if len(rendered) > max_chars:
        rendered = rendered[: max(0, max_chars - 1)].rstrip()
        truncated = True
    if truncated and rendered:
        rendered = rendered.rstrip(" .")
        if not rendered.endswith("…"):
            rendered += "…"
    return rendered


def _split_compound_command_display_parts(command_text: str) -> tuple[list[str], list[str]]:
    normalized = str(command_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return ([], [])
    segments: list[str] = []
    operators: list[str] = []
    current_segment: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(normalized):
        char = normalized[index]
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current_segment.append(char)
            index += 1
            continue
        if char == '"' and not in_single_quote:
            if index > 0 and normalized[index - 1] == "\\":
                current_segment.append(char)
                index += 1
                continue
            in_double_quote = not in_double_quote
            current_segment.append(char)
            index += 1
            continue
        if in_single_quote or in_double_quote:
            current_segment.append(char)
            index += 1
            continue
        if index + 1 < len(normalized):
            operator = normalized[index : index + 2]
            if operator in {"&&", "||"}:
                segment_text = "".join(current_segment).strip()
                if segment_text:
                    segments.append(segment_text)
                    operators.append(operator)
                current_segment = []
                index += 2
                continue
        if char == ";":
            segment_text = "".join(current_segment).strip()
            if segment_text:
                segments.append(segment_text)
                operators.append(";")
            current_segment = []
            index += 1
            continue
        current_segment.append(char)
        index += 1
    segment_text = "".join(current_segment).strip()
    if segment_text:
        segments.append(segment_text)
    return (segments, operators[: max(0, len(segments) - 1)])


def _is_shell_assignment_token(token: str) -> bool:
    return bool(_SHELL_ASSIGNMENT_RE.match(str(token or "").strip()))


def _trim_display_redirections(tokens: list[str]) -> list[str]:
    trimmed = list(tokens)
    while trimmed:
        if len(trimmed) >= 2 and trimmed[-2] in _REDIRECTION_OPERATOR_TOKENS:
            trimmed = trimmed[:-2]
            continue
        if _REDIRECTION_TOKEN_RE.match(str(trimmed[-1] or "").strip()):
            trimmed = trimmed[:-1]
            continue
        break
    return trimmed


def _display_tokens_for_segment(segment_text: str) -> list[str]:
    try:
        tokens = shlex.split(str(segment_text or "").strip(), posix=True)
    except ValueError:
        return []
    if not tokens:
        return []
    trimmed = list(tokens)
    while len(trimmed) > 1 and _is_shell_assignment_token(trimmed[0]):
        trimmed = trimmed[1:]
    if trimmed and all(_is_shell_assignment_token(token) for token in trimmed):
        return []
    return _trim_display_redirections(trimmed)


def _is_neutral_banner_display_segment(tokens: list[str]) -> bool:
    if not tokens:
        return False
    head = str(tokens[0] or "").strip().lower()
    if head not in {"echo", "printf", "true", "false", ":"}:
        return False
    return _trim_display_redirections(tokens) == tokens


def _is_skippable_display_segment(segment_text: str) -> bool:
    try:
        tokens = shlex.split(str(segment_text or "").strip(), posix=True)
    except ValueError:
        return False
    if not tokens:
        return True
    head = str(tokens[0] or "").strip()
    if not head:
        return True
    if head == "cd":
        return transcript_shell_exploration_command_helpers_runtime.cd_target(tokens[1:]) is not None
    if all(_is_shell_assignment_token(token) for token in tokens):
        return True
    if head in _SETUP_ONLY_COMMANDS:
        return True
    if _is_neutral_banner_display_segment(tokens):
        return True
    return transcript_shell_exploration_command_helpers_runtime.is_small_formatting_command(tokens)
