from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


def split_compound_command(command: str) -> list[str]:
    normalized = str(command or "").strip()
    if not normalized:
        return []

    segments: list[str] = []
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
            two_char = normalized[index : index + 2]
            if two_char in ("&&", "||"):
                segment_text = "".join(current_segment).strip()
                if segment_text:
                    segments.append(segment_text)
                current_segment = []
                index += 2
                continue

        if char == ";":
            segment_text = "".join(current_segment).strip()
            if segment_text:
                segments.append(segment_text)
            current_segment = []
            index += 1
            continue

        current_segment.append(char)
        index += 1

    segment_text = "".join(current_segment).strip()
    if segment_text:
        segments.append(segment_text)

    return segments


def validate_compound_command_segments(
    command: str,
    *,
    dangerous_builtins: set[str],
) -> dict[str, Any]:
    segments = split_compound_command(command)
    if not segments:
        return {
            "segments": [],
            "safe": True,
            "error_code": "",
            "error_message": "",
            "dangerous_constructs": [],
        }

    dangerous_constructs: list[str] = []
    for segment in segments:
        in_single_quote = False
        in_double_quote = False
        index = 0

        while index < len(segment):
            char = segment[index]

            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                index += 1
                continue

            if char == '"' and not in_single_quote:
                if index > 0 and segment[index - 1] == "\\":
                    index += 1
                    continue
                in_double_quote = not in_double_quote
                index += 1
                continue

            if in_single_quote:
                index += 1
                continue

            if char == "(" and not in_double_quote:
                dangerous_constructs.append(f"subshell in segment: {segment[:50]}")
                break

            if char == "$" and index + 1 < len(segment) and segment[index + 1] == "(":
                dangerous_constructs.append(f"command substitution $(...) in segment: {segment[:50]}")
                break

            if char == "`":
                dangerous_constructs.append(f"backtick command substitution in segment: {segment[:50]}")
                break

            if char == "$" and index + 1 < len(segment):
                next_char = segment[index + 1]
                if next_char.isalnum() or next_char == "_" or next_char == "{":
                    dangerous_constructs.append(f"variable expansion in segment: {segment[:50]}")
                    break

            index += 1

        try:
            tokens = shlex.split(segment)
            if tokens and tokens[0] in dangerous_builtins:
                dangerous_constructs.append(f"dangerous builtin '{tokens[0]}' in segment: {segment[:50]}")
        except ValueError:
            dangerous_constructs.append(f"unparseable segment: {segment[:50]}")

    if dangerous_constructs:
        return {
            "segments": segments,
            "safe": False,
            "error_code": "compound_command_dangerous_construct",
            "error_message": (
                "compound command contains dangerous constructs: "
                f"{'; '.join(dangerous_constructs[:3])}"
            ),
            "dangerous_constructs": dangerous_constructs,
        }

    return {
        "segments": segments,
        "safe": True,
        "error_code": "",
        "error_message": "",
        "dangerous_constructs": [],
    }


def contains_compound_operator(command: str, *, compound_operators: tuple[str, ...]) -> bool:
    text = str(command or "")
    return any(operator in text for operator in compound_operators)


def safe_split_command(command: str) -> list[str]:
    try:
        return shlex.split(str(command or "").strip(), posix=True)
    except ValueError:
        return []


def test_command_info(
    argv: list[str],
    *,
    blocked_test_runners: set[str],
) -> dict[str, Any]:
    if not argv:
        return {"is_test_command": False, "kind": "", "argv_start": 0}
    head = Path(str(argv[0] or "")).name.lower()
    if head in {"pytest", "py.test"}:
        return {"is_test_command": True, "kind": "pytest", "argv_start": 1}
    if len(argv) >= 3 and looks_like_python_launcher(head) and argv[1] == "-m" and str(argv[2] or "").lower() == "pytest":
        return {"is_test_command": True, "kind": "pytest", "argv_start": 3}
    if head in blocked_test_runners:
        return {"is_test_command": True, "kind": head, "argv_start": 1}
    if head in {"npm", "pnpm", "yarn"} and len(argv) >= 2 and str(argv[1] or "").lower() == "test":
        return {"is_test_command": True, "kind": f"{head}_test", "argv_start": 2}
    if head == "go" and len(argv) >= 2 and str(argv[1] or "").lower() == "test":
        return {"is_test_command": True, "kind": "go_test", "argv_start": 2}
    if head == "cargo" and len(argv) >= 2 and str(argv[1] or "").lower() == "test":
        return {"is_test_command": True, "kind": "cargo_test", "argv_start": 2}
    return {"is_test_command": False, "kind": "", "argv_start": 0}


def looks_like_python_launcher(name: str) -> bool:
    normalized = str(name or "").strip().lower()
    return normalized == "py" or normalized.startswith("python")


def explicit_pytest_targets(
    argv: list[str],
    *,
    start_index: int,
    pytest_options_with_value: set[str],
) -> list[str]:
    targets: list[str] = []
    passthrough = False
    index = max(0, int(start_index))
    while index < len(argv):
        token = str(argv[index] or "")
        if not token:
            index += 1
            continue
        if passthrough:
            if is_explicit_pytest_target(token):
                targets.append(token)
            index += 1
            continue
        if token == "--":
            passthrough = True
            index += 1
            continue
        if token.startswith("-"):
            if pytest_option_consumes_value(token, pytest_options_with_value=pytest_options_with_value):
                index += 2
                continue
            index += 1
            continue
        if is_explicit_pytest_target(token):
            targets.append(token)
        index += 1
    return targets


def pytest_option_consumes_value(token: str, *, pytest_options_with_value: set[str]) -> bool:
    if token in pytest_options_with_value:
        return True
    if token.startswith("--") and "=" in token:
        return False
    short_with_value = ("-k", "-m", "-c", "-o")
    return any(token.startswith(prefix) and token != prefix for prefix in short_with_value)


def is_explicit_pytest_target(token: str) -> bool:
    normalized = str(token or "").strip()
    if not normalized or normalized in {".", "./"}:
        return False
    if "::" in normalized:
        return True
    path_text = normalized.split("[", 1)[0]
    return Path(path_text).suffix.lower() == ".py"
