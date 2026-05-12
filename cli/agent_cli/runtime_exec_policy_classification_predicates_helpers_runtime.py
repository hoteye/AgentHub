from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_exec_policy_classification_parsing_helpers_runtime import (
    _split_command_segments,
)
from cli.agent_cli.runtime_exec_policy_classification_predicates_tables_runtime import (
    _DANGEROUS_FIND_FLAGS,
    _DANGEROUS_GIT_PREFIXES,
    _DANGEROUS_PROGRAMS,
    _NETWORK_GIT_SUBCOMMANDS,
    _NETWORK_PROGRAMS,
    _NETWORK_SCHEMES,
    _SAFE_GIT_SUBCOMMANDS,
    _SAFE_READ_PROGRAMS,
    _SHELL_WRAPPERS,
    _WRITE_GIT_SUBCOMMANDS,
    _WRITE_PROGRAMS,
)
from cli.agent_cli.runtime_exec_policy_shell_text_parsing_runtime import (
    _extract_command_substitutions,
    _segment_security_flags,
)
from cli.agent_cli.runtime_services import (
    command_policy_pure_helpers_runtime as command_policy_helpers,
)


def _command_substitutions_are_safe_read_only(text: str) -> bool:
    substitutions = _extract_command_substitutions(text)
    if not substitutions:
        return False
    return all(_command_text_is_safe_read_only(command) for command in substitutions)


def _command_text_is_safe_read_only(command: str) -> bool:
    segments = _split_command_segments(command)
    if not segments:
        return False
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        argv = command_policy_helpers.safe_split_command(text)
        flags = _segment_security_flags(text)
        if (
            flags["has_command_substitution"]
            or flags["has_backticks"]
            or flags["has_subshell"]
            or flags["has_heredoc"]
        ):
            return False
        program = _program_name(argv)
        if _is_dangerous_git_command(argv) or _is_dangerous_find_command(argv):
            return False
        if not _is_safe_read_segment(program, argv, flags=flags):
            return False
    return True


def _classify_segment(
    text: str,
    *,
    argv: list[str],
    program: str,
    flags: dict[str, bool],
) -> dict[str, Any]:
    safe_command_substitutions = bool(
        flags["has_command_substitution"]
        and not flags["has_backticks"]
        and not flags["has_heredoc"]
        and program in _SAFE_READ_PROGRAMS
        and not _writes_to_filesystem(program, argv, flags=flags)
        and _command_substitutions_are_safe_read_only(text)
    )
    if (
        flags["has_backticks"]
        or flags["has_heredoc"]
        or (flags["has_command_substitution"] and not safe_command_substitutions)
        or (flags["has_subshell"] and not safe_command_substitutions)
    ):
        return {
            "classification": "dangerous",
            "reason_code": "segment.dangerous.shell_construct",
            "reason_text": "Segment uses shell constructs that bypass transparent command classification.",
            "rule_id": "dangerous_shell_construct",
            "writes_to_filesystem": bool(flags["has_unsafe_output_redirection"]),
            "uses_network": False,
            "base_decision": "prompt",
        }

    if not argv:
        return {
            "classification": "opaque",
            "reason_code": "segment.opaque.unparsed",
            "reason_text": "Segment could not be tokenized cleanly and is treated as opaque.",
            "rule_id": "opaque_unparsed_segment",
            "writes_to_filesystem": bool(flags["has_unsafe_output_redirection"]),
            "uses_network": False,
            "base_decision": "prompt",
        }

    if program in _DANGEROUS_PROGRAMS:
        return {
            "classification": "dangerous",
            "reason_code": f"segment.dangerous.{program}",
            "reason_text": f"Program '{program}' is treated as dangerous.",
            "rule_id": f"dangerous_program_{program}",
            "writes_to_filesystem": True,
            "uses_network": False,
            "base_decision": "prompt",
        }

    if program in _SHELL_WRAPPERS:
        return {
            "classification": "dangerous",
            "reason_code": f"segment.dangerous.{program}_wrapper",
            "reason_text": f"Program '{program}' wraps another shell command and is treated as dangerous.",
            "rule_id": f"dangerous_shell_wrapper_{program}",
            "writes_to_filesystem": bool(flags["has_unsafe_output_redirection"]),
            "uses_network": False,
            "base_decision": "prompt",
        }

    if _is_dangerous_git_command(argv):
        return {
            "classification": "dangerous",
            "reason_code": "segment.dangerous.git_mutation",
            "reason_text": "Git segment includes a destructive mutation pattern.",
            "rule_id": "dangerous_git_command",
            "writes_to_filesystem": True,
            "uses_network": False,
            "base_decision": "prompt",
        }

    if _is_dangerous_find_command(argv):
        return {
            "classification": "dangerous",
            "reason_code": "segment.dangerous.find_exec",
            "reason_text": "Find segment includes execution or deletion flags.",
            "rule_id": "dangerous_find_command",
            "writes_to_filesystem": True,
            "uses_network": False,
            "base_decision": "prompt",
        }

    if _is_safe_read_segment(program, argv, flags=flags):
        return {
            "classification": "safe_read",
            "reason_code": f"segment.safe_read.{program}",
            "reason_text": f"Program '{program}' matched the safe read allowlist.",
            "rule_id": f"safe_read_{program}",
            "writes_to_filesystem": False,
            "uses_network": False,
            "base_decision": "allow",
        }

    writes_to_filesystem = _writes_to_filesystem(program, argv, flags=flags)
    if writes_to_filesystem:
        return {
            "classification": "write",
            "reason_code": f"segment.write.{program or 'unknown'}",
            "reason_text": "Segment appears to modify the filesystem or repository state.",
            "rule_id": f"write_segment_{program or 'unknown'}",
            "writes_to_filesystem": True,
            "uses_network": _uses_network(program, argv),
            "base_decision": "prompt",
        }

    if _uses_network(program, argv):
        return {
            "classification": "network",
            "reason_code": f"segment.network.{program or 'unknown'}",
            "reason_text": "Segment appears to perform network access.",
            "rule_id": f"network_segment_{program or 'unknown'}",
            "writes_to_filesystem": False,
            "uses_network": True,
            "base_decision": "prompt",
        }

    return {
        "classification": "opaque",
        "reason_code": f"segment.opaque.{program or 'unknown'}",
        "reason_text": "Segment is not on the safe read allowlist and is treated as opaque.",
        "rule_id": f"opaque_segment_{program or 'unknown'}",
        "writes_to_filesystem": False,
        "uses_network": False,
        "base_decision": "prompt",
    }


def _is_safe_read_segment(program: str, argv: list[str], *, flags: dict[str, bool]) -> bool:
    if not program or program not in _SAFE_READ_PROGRAMS:
        return False
    if flags["has_unsafe_output_redirection"]:
        return False
    if program in {
        "cat",
        "grep",
        "head",
        "id",
        "ls",
        "pwd",
        "readlink",
        "realpath",
        "rg",
        "stat",
        "tail",
        "uname",
        "wc",
        "which",
    }:
        return True
    if program == "git":
        return len(argv) >= 2 and str(argv[1] or "").strip().lower() in _SAFE_GIT_SUBCOMMANDS
    if program == "find":
        return not _is_dangerous_find_command(argv)
    if program == "sed":
        lowered = {str(token or "").strip().lower() for token in argv[1:]}
        return (
            bool({"-n", "--quiet", "--silent"} & lowered)
            and "-i" not in lowered
            and "--in-place" not in lowered
        )
    return False


def _writes_to_filesystem(program: str, argv: list[str], *, flags: dict[str, bool]) -> bool:
    if flags["has_unsafe_output_redirection"]:
        return True
    if not program:
        return False
    if program == "find":
        return _is_dangerous_find_command(argv)
    if program == "sed":
        lowered = {str(token or "").strip().lower() for token in argv[1:]}
        return "-i" in lowered or "--in-place" in lowered
    if program == "git":
        return _is_write_git_command(argv)
    if program in {"python", "python3"} and len(argv) >= 3 and argv[1] == "-m":
        return str(argv[2] or "").strip().lower() in {"pip", "pip3"}
    return program in _WRITE_PROGRAMS


def _uses_network(program: str, argv: list[str]) -> bool:
    if not program:
        return False
    if program in _NETWORK_PROGRAMS:
        return True
    if program == "git" and len(argv) >= 2:
        return str(argv[1] or "").strip().lower() in _NETWORK_GIT_SUBCOMMANDS
    return any(_looks_like_network_target(token) for token in argv[1:])


def _looks_like_network_target(token: str) -> bool:
    normalized = str(token or "").strip().lower()
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in _NETWORK_SCHEMES):
        return True
    if "=" in normalized:
        _prefix, _separator, candidate = normalized.partition("=")
        if any(candidate.startswith(prefix) for prefix in _NETWORK_SCHEMES):
            return True
    return False


def _is_dangerous_find_command(argv: list[str]) -> bool:
    lowered = {str(token or "").strip().lower() for token in argv[1:]}
    return bool(lowered & _DANGEROUS_FIND_FLAGS)


def _is_dangerous_git_command(argv: list[str]) -> bool:
    if len(argv) < 2 or _program_name(argv) != "git":
        return False
    normalized = [str(token or "").strip().lower() for token in argv[1:]]
    if not normalized:
        return False
    for prefix in _DANGEROUS_GIT_PREFIXES:
        if tuple(normalized[: len(prefix)]) == prefix:
            return True
    return False


def _is_write_git_command(argv: list[str]) -> bool:
    if len(argv) < 2 or _program_name(argv) != "git":
        return False
    subcommand = str(argv[1] or "").strip().lower()
    if subcommand in _SAFE_GIT_SUBCOMMANDS:
        return False
    if _is_dangerous_git_command(argv):
        return True
    return subcommand in _WRITE_GIT_SUBCOMMANDS


def _program_name(argv: list[str]) -> str:
    if not argv:
        return ""
    return Path(str(argv[0] or "")).name.strip().lower()


def _suggest_rule_prefix(argv: list[str], *, classification: str) -> list[str]:
    if not argv:
        return []
    if classification == "safe_read" and len(argv) >= 2 and _program_name(argv) in {"git", "sed"}:
        return [str(argv[0]), str(argv[1])]
    return [str(argv[0])]


__all__ = [
    "_classify_segment",
    "_program_name",
    "_segment_security_flags",
    "_suggest_rule_prefix",
]
