from __future__ import annotations

from cli.agent_cli.ui.transcript_shell_exploration_command_normalization_helpers_runtime import (
    _short_display_path,
)


def is_small_formatting_command(tokens: list[str]) -> bool:
    if not tokens:
        return False
    head = tokens[0]
    if head in {"yes", "y", "no", "n", "true", "wc", "tr", "cut", "sort", "uniq", "tee", "column", "printf"}:
        return True
    if head == "awk":
        return _awk_data_file_operand(tokens[1:]) is None
    if head == "head":
        if len(tokens) == 1:
            return True
        if len(tokens) == 2:
            return tokens[1].startswith("-")
        if len(tokens) == 3 and tokens[1] in {"-n", "-c"} and tokens[2].isdigit():
            return True
        return False
    if head == "tail":
        if len(tokens) == 1:
            return True
        if len(tokens) == 2:
            return tokens[1].startswith("-")
        if len(tokens) == 3 and tokens[1] in {"-n", "-c"}:
            count = tokens[2][1:] if tokens[2].startswith("+") else tokens[2]
            return bool(count) and count.isdigit()
        return False
    if head == "sed":
        return _sed_read_path(tokens[1:]) is None
    return False


def is_skippable_banner_command(tokens: list[str]) -> bool:
    if not tokens:
        return False
    head = str(tokens[0] or "").strip().lower()
    return head in {"echo", "printf", "true", "false", ":"}


def _skip_flag_values(args: list[str], flags_with_values: set[str]) -> list[str]:
    output: list[str] = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--":
            output.extend(args[index + 1 :])
            break
        if arg.startswith("--") and "=" in arg:
            continue
        if arg in flags_with_values:
            if index + 1 < len(args):
                skip_next = True
            continue
        output.append(arg)
    return output


def _positional_operands(args: list[str], flags_with_values: set[str]) -> list[str]:
    output: list[str] = []
    after_double_dash = False
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if after_double_dash:
            output.append(arg)
            continue
        if arg == "--":
            after_double_dash = True
            continue
        if arg.startswith("--") and "=" in arg:
            continue
        if arg in flags_with_values:
            if index + 1 < len(args):
                skip_next = True
            continue
        if arg.startswith("-"):
            continue
        output.append(arg)
    return output


def _first_non_flag_operand(args: list[str], flags_with_values: set[str]) -> str | None:
    operands = _positional_operands(args, flags_with_values)
    return operands[0] if operands else None


def _single_non_flag_operand(args: list[str], flags_with_values: set[str]) -> str | None:
    operands = _positional_operands(args, flags_with_values)
    if len(operands) != 1:
        return None
    return operands[0]


def _is_pathish(value: str) -> bool:
    text = str(value or "")
    return text in {".", ".."} or text.startswith("./") or text.startswith("../") or "/" in text or "\\" in text


def _parse_fd_query_and_path(args: list[str]) -> tuple[str | None, str | None]:
    candidates = _skip_flag_values(
        args,
        {"-t", "--type", "-e", "--extension", "-E", "--exclude", "--search-path"},
    )
    non_flags = [item for item in candidates if not item.startswith("-")]
    if len(non_flags) == 1:
        if _is_pathish(non_flags[0]):
            return None, _short_display_path(non_flags[0])
        return non_flags[0], None
    if len(non_flags) >= 2:
        return non_flags[0], _short_display_path(non_flags[1])
    return None, None


def _parse_find_query_and_path(args: list[str]) -> tuple[str | None, str | None]:
    path: str | None = None
    for arg in args:
        if not arg.startswith("-") and arg not in {"!", "(", ")"}:
            path = _short_display_path(arg)
            break
    query: str | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-name", "-iname", "-path", "-regex"} and index + 1 < len(args):
            query = args[index + 1]
            break
        index += 1
    return query, path


def _parse_grep_like(args: list[str]) -> tuple[str | None, str | None]:
    operands: list[str] = []
    pattern: str | None = None
    after_double_dash = False
    index = 0
    while index < len(args):
        arg = args[index]
        if after_double_dash:
            operands.append(arg)
            index += 1
            continue
        if arg == "--":
            after_double_dash = True
            index += 1
            continue
        if arg in {"-e", "--regexp", "-f", "--file"}:
            if index + 1 < len(args) and pattern is None:
                pattern = args[index + 1]
            index += 2
            continue
        if arg in {"-m", "--max-count", "-C", "--context", "-A", "--after-context", "-B", "--before-context"}:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        operands.append(arg)
        index += 1
    has_pattern = pattern is not None
    query = pattern or (operands[0] if operands else None)
    path_index = 0 if has_pattern else 1
    path = operands[path_index] if len(operands) > path_index else None
    return query, path


def _awk_data_file_operand(args: list[str]) -> str | None:
    if not args:
        return None
    has_script_file = any(arg in {"-f", "--file"} for arg in args)
    candidates = _skip_flag_values(
        args,
        {"-F", "-v", "-f", "--field-separator", "--assign", "--file"},
    )
    non_flags = [arg for arg in candidates if not arg.startswith("-")]
    if has_script_file:
        return non_flags[0] if non_flags else None
    if len(non_flags) >= 2:
        return non_flags[1]
    return None


def _is_valid_sed_n_arg(arg: str | None) -> bool:
    text = str(arg or "").strip()
    if not text or not text.endswith("p"):
        return False
    core = text[:-1]
    parts = core.split(",")
    if len(parts) == 1:
        return bool(parts[0]) and parts[0].isdigit()
    if len(parts) == 2:
        return bool(parts[0]) and bool(parts[1]) and parts[0].isdigit() and parts[1].isdigit()
    return False


def _sed_read_path(args: list[str]) -> str | None:
    if "-n" not in args:
        return None
    has_range_script = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-e", "--expression"}:
            if index + 1 < len(args) and _is_valid_sed_n_arg(args[index + 1]):
                has_range_script = True
            index += 2
            continue
        if arg in {"-f", "--file"}:
            index += 2
            continue
        index += 1
    if not has_range_script:
        has_range_script = any(not arg.startswith("-") and _is_valid_sed_n_arg(arg) for arg in args)
    if not has_range_script:
        return None
    candidates = _skip_flag_values(args, {"-e", "-f", "--expression", "--file"})
    non_flags = [arg for arg in candidates if not arg.startswith("-")]
    if not non_flags:
        return None
    if _is_valid_sed_n_arg(non_flags[0]):
        return non_flags[1] if len(non_flags) >= 2 else None
    return non_flags[0]
