"""Pure shell-text parsing helpers for command security classification.

These functions analyse raw shell command text for security-relevant
constructs (output redirection, command substitution, backticks, subshells,
heredocs) without depending on any program-name allow/deny constant sets.
They are consumed by the classification predicates module.
"""

from __future__ import annotations


def _segment_security_flags(text: str) -> dict[str, bool]:
    normalized = str(text or "")
    in_single_quote = False
    in_double_quote = False
    has_output_redirection = False
    has_command_substitution = False
    has_backticks = False
    has_subshell = False
    has_heredoc = False
    index = 0

    while index < len(normalized):
        char = normalized[index]

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            index += 1
            continue

        if char == '"' and not in_single_quote:
            if index > 0 and normalized[index - 1] == "\\":
                index += 1
                continue
            in_double_quote = not in_double_quote
            index += 1
            continue

        if in_single_quote:
            index += 1
            continue

        if char == "`":
            has_backticks = True
        elif char == "$" and normalized[index + 1 : index + 2] == "(":
            has_command_substitution = True
            has_subshell = True
        elif char == "(" and not in_double_quote and index == 0:
            has_subshell = True
        elif char == "<":
            next_char = normalized[index + 1 : index + 2]
            if next_char == "<":
                has_heredoc = True
        elif char == ">":
            has_output_redirection = True

        index += 1

    stripped = normalized.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        has_subshell = True

    return {
        "has_output_redirection": has_output_redirection,
        "has_unsafe_output_redirection": _has_unsafe_output_redirection(normalized),
        "has_command_substitution": has_command_substitution,
        "has_backticks": has_backticks,
        "has_subshell": has_subshell,
        "has_heredoc": has_heredoc,
    }


def _has_unsafe_output_redirection(text: str) -> bool:
    normalized = str(text or "")
    in_single_quote = False
    in_double_quote = False
    index = 0

    while index < len(normalized):
        char = normalized[index]
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            index += 1
            continue
        if char == '"' and not in_single_quote:
            if index > 0 and normalized[index - 1] == "\\":
                index += 1
                continue
            in_double_quote = not in_double_quote
            index += 1
            continue
        if in_single_quote or in_double_quote:
            index += 1
            continue
        if char == "$" and normalized[index + 1 : index + 2] == "(":
            skipped_index = _skip_command_substitution(normalized, index)
            if skipped_index is None:
                return True
            index = skipped_index
            continue
        if char != ">":
            index += 1
            continue

        next_index = index + 1
        if next_index < len(normalized) and normalized[next_index] == ">":
            next_index += 1
        while next_index < len(normalized) and normalized[next_index].isspace():
            next_index += 1
        target_start = next_index
        while next_index < len(normalized) and not normalized[next_index].isspace():
            next_index += 1
        target = normalized[target_start:next_index].strip()
        if target not in {"/dev/null", "&1", "&2"}:
            return True
        index = next_index

    return False


def _skip_command_substitution(text: str, start_index: int) -> int | None:
    if text[start_index : start_index + 2] != "$(":
        return None
    depth = 1
    cursor = start_index + 2
    in_single_quote = False
    in_double_quote = False

    while cursor < len(text):
        char = text[cursor]
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            cursor += 1
            continue
        if char == '"' and not in_single_quote:
            if cursor > start_index + 2 and text[cursor - 1] == "\\":
                cursor += 1
                continue
            in_double_quote = not in_double_quote
            cursor += 1
            continue
        if in_single_quote:
            cursor += 1
            continue
        if char == "$" and text[cursor + 1 : cursor + 2] == "(":
            depth += 1
            cursor += 2
            continue
        if char == ")" and not in_double_quote:
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return None


def _extract_command_substitutions(text: str) -> list[str]:
    normalized = str(text or "")
    substitutions: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0

    while index < len(normalized):
        char = normalized[index]
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            index += 1
            continue
        if char == '"' and not in_single_quote:
            if index > 0 and normalized[index - 1] == "\\":
                index += 1
                continue
            in_double_quote = not in_double_quote
            index += 1
            continue
        if in_single_quote:
            index += 1
            continue
        if char != "$" or normalized[index + 1 : index + 2] != "(":
            index += 1
            continue

        start = index + 2
        depth = 1
        cursor = start
        inner_single_quote = False
        inner_double_quote = False
        while cursor < len(normalized):
            inner_char = normalized[cursor]
            if inner_char == "'" and not inner_double_quote:
                inner_single_quote = not inner_single_quote
                cursor += 1
                continue
            if inner_char == '"' and not inner_single_quote:
                if cursor > start and normalized[cursor - 1] == "\\":
                    cursor += 1
                    continue
                inner_double_quote = not inner_double_quote
                cursor += 1
                continue
            if inner_single_quote:
                cursor += 1
                continue
            if inner_char == "$" and normalized[cursor + 1 : cursor + 2] == "(":
                depth += 1
                cursor += 2
                continue
            if inner_char == ")" and not inner_double_quote:
                depth -= 1
                if depth == 0:
                    substitutions.append(normalized[start:cursor].strip())
                    index = cursor + 1
                    break
            cursor += 1
        else:
            return []

    return substitutions


__all__ = [
    "_extract_command_substitutions",
    "_segment_security_flags",
]
