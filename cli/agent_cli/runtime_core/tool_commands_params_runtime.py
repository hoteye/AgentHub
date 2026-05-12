from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple


def parse_plugin_install_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    return {
        "path": str(options.get("path") or (positionals[0] if positionals else "")).strip(),
        "replace": bool(options.get("replace")),
        "scope": str(options.get("scope") or "user").strip() or "user",
    }


def parse_glob_files_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    pattern = str(options.get("pattern") or " ".join(positionals)).strip()
    target_path = str(options.get("path") or "").strip() or None
    limit_value = options.get("limit")
    return {
        "pattern": pattern,
        "path": target_path,
        "limit": int(limit_value) if limit_value is not None else 100,
    }


def parse_grep_files_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    pattern = str(options.get("pattern") or " ".join(positionals)).strip()
    include = str(options.get("include") or "").strip() or None
    target_path = str(options.get("path") or "").strip() or None
    limit_value = options.get("limit")
    output_mode = str(options.get("output-mode") or options.get("output_mode") or "files_with_matches").strip()
    file_type = str(options.get("type") or "").strip() or None
    after_context_value = options.get("after") or options.get("after-context")
    before_context_value = options.get("before") or options.get("before-context")
    context_value = options.get("context")
    offset_value = options.get("offset")
    return {
        "pattern": pattern,
        "include": include,
        "path": target_path,
        "limit": int(limit_value) if limit_value is not None else 100,
        "output_mode": output_mode if output_mode in {"files_with_matches", "content", "count"} else "files_with_matches",
        "case_insensitive": bool(options.get("case-insensitive") or options.get("ignore-case")),
        "file_type": file_type,
        "line_numbers": bool(options.get("line-numbers") or options.get("line-number")),
        "after_context": int(after_context_value) if after_context_value is not None else None,
        "before_context": int(before_context_value) if before_context_value is not None else None,
        "context": int(context_value) if context_value is not None else None,
        "offset": int(offset_value) if offset_value is not None else 0,
        "multiline": bool(options.get("multiline")),
    }


def parse_list_dir_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    target_path = str(options.get("dir-path") or options.get("path") or " ".join(positionals)).strip() or None
    offset_value = options.get("offset")
    limit_value = options.get("limit")
    depth_value = options.get("depth")
    return {
        "dir_path": target_path,
        "offset": int(offset_value) if offset_value is not None else 1,
        "limit": int(limit_value) if limit_value is not None else 25,
        "depth": int(depth_value) if depth_value is not None else 2,
    }


def parse_read_file_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    file_path = str(options.get("file-path") or options.get("path") or " ".join(positionals)).strip()
    offset_value = options.get("offset")
    limit_value = options.get("limit")
    mode = str(options.get("mode") or "").strip() or None
    indentation = _parse_indentation_json(str(options.get("indentation") or "").strip())
    return {
        "file_path": file_path,
        "offset": int(offset_value) if offset_value is not None else None,
        "limit": int(limit_value) if limit_value is not None else None,
        "mode": mode,
        "indentation": indentation,
    }


def read_file_arguments(parsed: Dict[str, Any]) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {"file_path": parsed["file_path"]}
    if parsed["offset"] is not None:
        arguments["offset"] = parsed["offset"]
    if parsed["limit"] is not None:
        arguments["limit"] = parsed["limit"]
    if parsed["mode"] is not None:
        arguments["mode"] = parsed["mode"]
    if parsed["indentation"] is not None:
        arguments["indentation"] = parsed["indentation"]
    return arguments


def parse_file_list_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    target_path = str(options.get("path") or " ".join(positionals)).strip() or None
    limit_value = options.get("limit")
    return {
        "path": target_path,
        "limit": int(limit_value) if limit_value is not None else 50,
    }


def parse_file_search_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    query = " ".join(positionals).strip()
    target_path = str(options.get("path") or "").strip() or None
    limit_value = options.get("limit")
    return {
        "query": query,
        "path": target_path,
        "limit": int(limit_value) if limit_value is not None else 20,
    }


def parse_file_read_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    target_path = str(options.get("path") or " ".join(positionals)).strip()
    offset_value = options.get("offset")
    limit_value = options.get("limit")
    max_chars_value = options.get("max-chars")
    return {
        "path": target_path,
        "offset": int(offset_value) if offset_value is not None else None,
        "limit": int(limit_value) if limit_value is not None else None,
        "max_chars": int(max_chars_value) if max_chars_value is not None else None,
    }


def file_read_arguments(parsed: Dict[str, Any]) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {"path": parsed["path"]}
    if parsed["offset"] is not None:
        arguments["offset"] = parsed["offset"]
    if parsed["limit"] is not None:
        arguments["limit"] = parsed["limit"]
    if parsed["max_chars"] is not None:
        arguments["max_chars"] = parsed["max_chars"]
    return arguments


def parse_office_run_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    args: Dict[str, Any] = {}
    if options.get("path"):
        args["path"] = options["path"]
    return {
        "positionals": positionals,
        "skill_name": positionals[0] if positionals else "",
        "args": args,
    }


def parse_view_image_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> str:
    positionals, options = parse_args_fn(arg_text)
    return str(options.get("path") or " ".join(positionals)).strip()


def parse_web_search_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    query = " ".join(positionals).strip()
    raw_domains = str(options.get("domains") or options.get("domain") or "").strip()
    domains = [item.strip() for item in raw_domains.split(",") if item.strip()] or None
    raw_blocked = str(options.get("blocked-domains") or options.get("blocked_domains") or "").strip()
    blocked_domains = [item.strip() for item in raw_blocked.split(",") if item.strip()] or None
    limit_value = options.get("limit")
    recency_value = options.get("recency-days")
    return {
        "query": query,
        "limit": int(limit_value) if limit_value is not None else 5,
        "domains": domains,
        "blocked_domains": blocked_domains,
        "recency_days": int(recency_value) if recency_value is not None else None,
        "market": str(options.get("market") or "").strip() or None,
    }


def parse_web_fetch_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    max_chars_value = options.get("max-chars")
    return {
        "url": " ".join(positionals).strip(),
        "max_chars": int(max_chars_value) if max_chars_value is not None else 12000,
    }


def parse_open_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Dict[str, Any]:
    positionals, options = parse_args_fn(arg_text)
    line_value = options.get("line")
    return {
        "ref": " ".join(positionals).strip(),
        "line": int(line_value) if line_value is not None else 1,
    }


def parse_click_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Tuple[List[str], Dict[str, Any]]:
    positionals, options = parse_args_fn(arg_text)
    return positionals, options


def parse_find_args(parse_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]], arg_text: str) -> Tuple[List[str], Dict[str, Any]]:
    positionals, options = parse_args_fn(arg_text)
    return positionals, options


def _parse_indentation_json(value: str) -> Dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict):
        return parsed
    return None
