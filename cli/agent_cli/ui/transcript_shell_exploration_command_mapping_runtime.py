from __future__ import annotations

from typing import Callable, TypeVar


SummaryT = TypeVar("SummaryT")


def parse_shell_segment(
    tokens: list[str],
    *,
    cwd: str | None,
    build_summary_fn: Callable[..., SummaryT],
    first_non_flag_operand_fn: Callable[[list[str], set[str]], str | None],
    skip_flag_values_fn: Callable[[list[str], set[str]], list[str]],
    display_list_subject_fn: Callable[[str | None], str],
    display_search_path_fn: Callable[[str | None], str | None],
    display_read_name_fn: Callable[[str], str],
    parse_grep_like_fn: Callable[[list[str]], tuple[str | None, str | None]],
    parse_fd_query_and_path_fn: Callable[[list[str]], tuple[str | None, str | None]],
    parse_find_query_and_path_fn: Callable[[list[str]], tuple[str | None, str | None]],
    single_non_flag_operand_fn: Callable[[list[str], set[str]], str | None],
    awk_data_file_operand_fn: Callable[[list[str]], str | None],
    sed_read_path_fn: Callable[[list[str]], str | None],
) -> SummaryT | None:
    if not tokens:
        return None
    head, tail = tokens[0], tokens[1:]
    if head in {"ls", "eza", "exa"}:
        path = first_non_flag_operand_fn(
            tail,
            {"-I", "-w", "--block-size", "--format", "--time-style", "--color", "--quoting-style", "--ignore-glob", "--sort", "--time"},
        )
        return build_summary_fn(kind="list", path=display_list_subject_fn(path))
    if head == "tree":
        path = first_non_flag_operand_fn(tail, {"-L", "-P", "-I", "--charset", "--filelimit", "--sort"})
        return build_summary_fn(kind="list", path=display_list_subject_fn(path))
    if head == "du":
        path = first_non_flag_operand_fn(tail, {"-d", "--max-depth", "-B", "--block-size", "--exclude", "--time-style"})
        return build_summary_fn(kind="list", path=display_list_subject_fn(path))
    if head in {"rg", "rga", "ripgrep-all"}:
        has_files_flag = "--files" in tail
        pattern: str | None = None
        non_flags: list[str] = []
        after_double_dash = False
        index = 0
        flags_with_values = {
            "-g",
            "--glob",
            "--iglob",
            "-t",
            "--type",
            "--type-add",
            "--type-not",
            "-m",
            "--max-count",
            "-A",
            "-B",
            "-C",
            "--context",
            "--max-depth",
        }
        while index < len(tail):
            arg = tail[index]
            if after_double_dash:
                non_flags.append(arg)
                index += 1
                continue
            if arg == "--":
                after_double_dash = True
                index += 1
                continue
            if arg in {"-e", "--regexp", "-f", "--file"}:
                if index + 1 < len(tail) and pattern is None:
                    pattern = tail[index + 1]
                index += 2
                continue
            if arg.startswith("--") and "=" in arg:
                option_name, option_value = arg.split("=", 1)
                if option_name in {"--regexp", "--file"} and pattern is None:
                    pattern = option_value
                index += 1
                continue
            if arg in flags_with_values:
                index += 2
                continue
            if arg.startswith("-"):
                index += 1
                continue
            non_flags.append(arg)
            index += 1
        if has_files_flag:
            path = non_flags[0] if non_flags else None
            return build_summary_fn(kind="list", path=display_list_subject_fn(path))
        has_pattern = pattern is not None
        query = pattern or (non_flags[0] if non_flags else None)
        path_index = 0 if has_pattern else 1
        path = non_flags[path_index] if len(non_flags) > path_index else None
        return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path))
    if head == "git" and tail:
        subcmd, sub_tail = tail[0], tail[1:]
        if subcmd == "grep":
            query, path = parse_grep_like_fn(sub_tail)
            return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path))
        if subcmd == "ls-files":
            path = first_non_flag_operand_fn(sub_tail, {"--exclude", "--exclude-from", "--pathspec-from-file"})
            return build_summary_fn(kind="list", path=display_list_subject_fn(path))
        return None
    if head == "fd":
        query, path = parse_fd_query_and_path_fn(tail)
        if query:
            return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path) if path else None)
        return build_summary_fn(kind="list", path=display_list_subject_fn(path))
    if head == "find":
        query, path = parse_find_query_and_path_fn(tail)
        if query:
            return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path) if path else None)
        return build_summary_fn(kind="list", path=display_list_subject_fn(path))
    if head in {"grep", "egrep", "fgrep"}:
        query, path = parse_grep_like_fn(tail)
        return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path))
    if head in {"ag", "ack", "pt"}:
        candidates = skip_flag_values_fn(
            tail,
            {"-G", "-g", "--file-search-regex", "--ignore-dir", "--ignore-file", "--path-to-ignore"},
        )
        non_flags = [item for item in candidates if not item.startswith("-")]
        query = non_flags[0] if non_flags else None
        path = non_flags[1] if len(non_flags) >= 2 else None
        return build_summary_fn(kind="search", query=query, path=display_search_path_fn(path))
    if head == "cat":
        path = single_non_flag_operand_fn(tail, set())
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head in {"bat", "batcat"}:
        path = single_non_flag_operand_fn(
            tail,
            {"--theme", "--language", "--style", "--terminal-width", "--tabs", "--line-range", "--map-syntax"},
        )
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "less":
        path = single_non_flag_operand_fn(
            tail,
            {"-p", "-P", "-x", "-y", "-z", "-j", "--pattern", "--prompt", "--tabs", "--shift", "--jump-target"},
        )
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "more":
        path = single_non_flag_operand_fn(tail, set())
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "head":
        path: str | None = None
        if tail[:2] and tail[0] == "-n" and len(tail) >= 3 and tail[1].isdigit():
            for candidate in tail[2:]:
                if not candidate.startswith("-"):
                    path = candidate
                    break
        elif tail and tail[0].startswith("-n") and tail[0][2:].isdigit():
            for candidate in tail[1:]:
                if not candidate.startswith("-"):
                    path = candidate
                    break
        elif len(tail) == 1 and not tail[0].startswith("-"):
            path = tail[0]
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "tail":
        path = None
        if tail[:2] and tail[0] == "-n" and len(tail) >= 3:
            count = tail[1][1:] if tail[1].startswith("+") else tail[1]
            if count.isdigit():
                for candidate in tail[2:]:
                    if not candidate.startswith("-"):
                        path = candidate
                        break
        elif tail and tail[0].startswith("-n"):
            count = tail[0][2:]
            count = count[1:] if count.startswith("+") else count
            if count.isdigit():
                for candidate in tail[1:]:
                    if not candidate.startswith("-"):
                        path = candidate
                        break
        elif len(tail) == 1 and not tail[0].startswith("-"):
            path = tail[0]
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "awk":
        path = awk_data_file_operand_fn(tail)
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "nl":
        candidates = skip_flag_values_fn(tail, {"-s", "-w", "-v", "-i", "-b"})
        path = next((candidate for candidate in candidates if not candidate.startswith("-")), None)
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    if head == "sed":
        path = sed_read_path_fn(tail)
        if not path:
            return None
        return build_summary_fn(kind="read", name=display_read_name_fn(path), path=path)
    return None
