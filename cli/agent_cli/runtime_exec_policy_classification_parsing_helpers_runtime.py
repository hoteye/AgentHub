from __future__ import annotations


def _split_command_segments(command: str) -> list[dict[str, str]]:
    normalized = str(command or "").strip()
    if not normalized:
        return []

    segments: list[dict[str, str]] = []
    current: list[str] = []
    pending_operator = ""
    in_single_quote = False
    in_double_quote = False
    index = 0

    def _push_current() -> None:
        text = "".join(current).strip()
        if text:
            segments.append({"operator": pending_operator, "text": text})

    while index < len(normalized):
        char = normalized[index]

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            index += 1
            continue

        if char == '"' and not in_single_quote:
            if index > 0 and normalized[index - 1] == "\\":
                current.append(char)
                index += 1
                continue
            in_double_quote = not in_double_quote
            current.append(char)
            index += 1
            continue

        if in_single_quote or in_double_quote:
            current.append(char)
            index += 1
            continue

        two_char = normalized[index : index + 2]
        if two_char in {"&&", "||"}:
            _push_current()
            current = []
            pending_operator = two_char
            index += 2
            continue

        if char in {"|", ";", "\n", "\r"}:
            _push_current()
            current = []
            pending_operator = char
            index += 1
            continue

        current.append(char)
        index += 1

    _push_current()
    return segments


__all__ = ["_split_command_segments"]
