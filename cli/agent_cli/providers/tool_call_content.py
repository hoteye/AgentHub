from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.host_platform import HostPlatform


def _quote_value(value: Any, quote_arg_fn: Callable[[Any], str]) -> str:
    return quote_arg_fn(str(value))

def content_tool_call_command(
    name: str,
    arguments: Dict[str, Any],
    host_platform: HostPlatform,
    *,
    quote_arg_fn: Callable[[Any], str],
) -> Optional[str]:
    # Platform is currently only threaded through for compatibility/alias
    # branches that recursively re-enter this command builder.
    _ = host_platform
    if name == "list_dir":
        path = str(arguments.get("dir_path") or arguments.get("path") or "").strip()
        offset = arguments.get("offset")
        limit = arguments.get("limit")
        depth = arguments.get("depth")
        command = "/list_dir"
        if path:
            command += f" {quote_arg_fn(path)}"
        if offset is not None:
            command += f" --offset {_quote_value(offset, quote_arg_fn)}"
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        if depth is not None:
            command += f" --depth {_quote_value(depth, quote_arg_fn)}"
        return command

    if name == "file_list":
        path = str(arguments.get("path") or "").strip()
        command = "/list_dir"
        if path:
            command += f" {quote_arg_fn(path)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        return command

    if name == "glob_files":
        pattern = str(arguments.get("pattern") or "").strip()
        if not pattern:
            return None
        command = f"/glob_files {quote_arg_fn(pattern)}"
        path = str(arguments.get("path") or "").strip()
        if path:
            command += f" --path {quote_arg_fn(path)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        return command

    if name == "grep_files":
        query = str(arguments.get("pattern") or arguments.get("query") or "").strip()
        if not query:
            return None
        command = f"/grep_files {quote_arg_fn(query)}"
        include = str(arguments.get("include") or "").strip()
        if include:
            command += f" --include {quote_arg_fn(include)}"
        path = str(arguments.get("path") or "").strip()
        if path:
            command += f" --path {quote_arg_fn(path)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        output_mode = str(arguments.get("output-mode") or "").strip()
        if output_mode in {"content", "files_with_matches", "count"}:
            command += f" --output-mode {quote_arg_fn(output_mode)}"
        file_type = str(arguments.get("type") or "").strip()
        if file_type:
            command += f" --type {quote_arg_fn(file_type)}"
        if arguments.get("case-insensitive") or arguments.get("ignore-case"):
            command += " --case-insensitive"
        if arguments.get("line-numbers") or arguments.get("line-number"):
            command += " --line-numbers"
        context = arguments.get("context")
        if context is not None:
            command += f" --context {_quote_value(context, quote_arg_fn)}"
        else:
            after = arguments.get("after") or arguments.get("after-context")
            before = arguments.get("before") or arguments.get("before-context")
            if after is not None:
                command += f" --after {_quote_value(after, quote_arg_fn)}"
            if before is not None:
                command += f" --before {_quote_value(before, quote_arg_fn)}"
        offset = arguments.get("offset")
        if offset is not None:
            command += f" --offset {_quote_value(offset, quote_arg_fn)}"
        if arguments.get("multiline"):
            command += " --multiline"
        return command

    if name == "file_search":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return None
        command = f"/grep_files {quote_arg_fn(query)}"
        path = str(arguments.get("path") or "").strip()
        if path:
            command += f" --path {quote_arg_fn(path)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        return command

    if name == "read_file":
        path = str(arguments.get("file_path") or arguments.get("path") or "").strip()
        if not path:
            return None
        command = f"/read_file {quote_arg_fn(path)}"
        offset = arguments.get("offset")
        if offset is not None:
            command += f" --offset {_quote_value(offset, quote_arg_fn)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        mode = str(arguments.get("mode") or "").strip()
        if mode:
            command += f" --mode {quote_arg_fn(mode)}"
        indentation = arguments.get("indentation")
        if isinstance(indentation, dict) and indentation:
            command += f" --indentation {quote_arg_fn(json.dumps(indentation, ensure_ascii=True))}"
        max_chars = arguments.get("max_chars")
        if max_chars is not None and offset is None and limit is None:
            command += f" --max-chars {_quote_value(max_chars, quote_arg_fn)}"
        return command

    if name == "file_read":
        path = str(arguments.get("path") or "").strip()
        if not path:
            return None
        command = f"/read_file {quote_arg_fn(path)}"
        offset = arguments.get("offset")
        if offset is not None:
            command += f" --offset {_quote_value(offset, quote_arg_fn)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        max_chars = arguments.get("max_chars")
        if max_chars is not None and offset is None and limit is None:
            command += f" --max-chars {_quote_value(max_chars, quote_arg_fn)}"
        return command

    if name == "office_skills":
        return "/office_skills"

    if name == "office_run":
        skill = str(arguments.get("skill") or "").strip()
        if not skill:
            return None
        command = f"/office_run {quote_arg_fn(skill)}"
        path = str(arguments.get("path") or "").strip()
        if path:
            command += f" --path {quote_arg_fn(path)}"
        return command

    if name == "web_search":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return None
        command = f"/web_search {quote_arg_fn(query)}"
        limit = arguments.get("limit")
        if limit is not None:
            command += f" --limit {_quote_value(limit, quote_arg_fn)}"
        domains = arguments.get("domains")
        if isinstance(domains, (list, tuple)):
            normalized = ",".join(str(item).strip() for item in domains if str(item).strip())
            if normalized:
                command += f" --domains {quote_arg_fn(normalized)}"
        blocked = arguments.get("blocked-domains") or arguments.get("blocked_domains")
        if blocked:
            if isinstance(blocked, (list, tuple)):
                blocked = ",".join(str(item).strip() for item in blocked if str(item).strip())
            blocked = str(blocked).strip()
            if blocked:
                command += f" --blocked-domains {quote_arg_fn(blocked)}"
        recency_days = arguments.get("recency_days")
        if recency_days is not None:
            command += f" --recency-days {_quote_value(recency_days, quote_arg_fn)}"
        market = str(arguments.get("market") or "").strip()
        if market:
            command += f" --market {quote_arg_fn(market)}"
        return command

    if name == "view_image":
        path = str(arguments.get("path") or "").strip()
        if not path:
            return None
        return f"/view_image {quote_arg_fn(path)}"

    if name == "web_fetch":
        url = str(arguments.get("url") or "").strip()
        if not url:
            return None
        command = f"/web_fetch {quote_arg_fn(url)}"
        max_chars = arguments.get("max_chars")
        if max_chars is not None:
            command += f" --max-chars {_quote_value(max_chars, quote_arg_fn)}"
        return command

    if name == "open":
        ref_value = str(arguments.get("ref") or arguments.get("url") or arguments.get("ref_id") or "").strip()
        if not ref_value:
            return None
        command = f"/browser open_legacy --ref {quote_arg_fn(ref_value)}"
        line = arguments.get("line")
        if line is not None:
            command += f" --line {_quote_value(line, quote_arg_fn)}"
        return command

    if name == "click":
        ref_id = str(arguments.get("ref_id") or "").strip()
        link_id = arguments.get("id")
        if not ref_id or link_id is None:
            return None
        return f"/browser click_legacy --ref {quote_arg_fn(ref_id)} --id {_quote_value(link_id, quote_arg_fn)}"

    if name == "find":
        ref_id = str(arguments.get("ref_id") or "").strip()
        pattern = str(arguments.get("pattern") or "").strip()
        if not ref_id or not pattern:
            return None
        return f"/browser find_legacy --ref {quote_arg_fn(ref_id)} --text {quote_arg_fn(pattern)}"

    if name == "Glob":
        pattern = str(arguments.get("pattern") or "").strip()
        if not pattern:
            return None
        mapped: Dict[str, Any] = {"pattern": pattern}
        path = str(arguments.get("path") or "").strip()
        if path:
            mapped["path"] = path
        return content_tool_call_command("glob_files", mapped, host_platform, quote_arg_fn=quote_arg_fn)

    if name == "Grep":
        mapped: Dict[str, Any] = {"pattern": arguments.get("pattern")}
        if arguments.get("path"):
            mapped["path"] = arguments["path"]
        glob_val = arguments.get("glob")
        if glob_val:
            mapped["include"] = glob_val
        if arguments.get("head_limit") is not None:
            mapped["limit"] = arguments["head_limit"]
        elif arguments.get("limit") is not None:
            mapped["limit"] = arguments["limit"]
        output_mode = str(arguments.get("output_mode") or "").strip()
        if output_mode in {"content", "files_with_matches", "count"}:
            mapped["output-mode"] = output_mode
        if arguments.get("type"):
            mapped["type"] = arguments["type"]
        if arguments.get("-i"):
            mapped["case-insensitive"] = True
        if arguments.get("-n"):
            mapped["line-numbers"] = True
        if arguments.get("-C") is not None:
            mapped["context"] = arguments["-C"]
        elif arguments.get("-A") is not None or arguments.get("-B") is not None:
            if arguments.get("-A") is not None:
                mapped["after"] = arguments["-A"]
            if arguments.get("-B") is not None:
                mapped["before"] = arguments["-B"]
        if arguments.get("offset") is not None:
            mapped["offset"] = arguments["offset"]
        if arguments.get("multiline"):
            mapped["multiline"] = True
        return content_tool_call_command("grep_files", mapped, host_platform, quote_arg_fn=quote_arg_fn)

    if name == "Read":
        return content_tool_call_command("read_file", arguments, host_platform, quote_arg_fn=quote_arg_fn)

    if name == "WebSearch":
        mapped = dict(arguments)
        if "allowed_domains" in mapped:
            mapped.setdefault("domains", mapped.pop("allowed_domains"))
        if "blocked_domains" in mapped:
            mapped["blocked-domains"] = ",".join(mapped.pop("blocked_domains")) if isinstance(mapped["blocked_domains"], list) else mapped.pop("blocked_domains")
        return content_tool_call_command("web_search", mapped, host_platform, quote_arg_fn=quote_arg_fn)

    if name == "WebFetch":
        mapped: Dict[str, Any] = {"url": arguments.get("url")}
        if arguments.get("max_chars") is not None:
            mapped["max_chars"] = arguments["max_chars"]
        return content_tool_call_command("web_fetch", mapped, host_platform, quote_arg_fn=quote_arg_fn)

    return None
