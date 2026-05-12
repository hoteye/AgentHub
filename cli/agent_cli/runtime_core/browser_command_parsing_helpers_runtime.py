from __future__ import annotations

import json
from typing import Any, Callable


def parse_flag_token_impl(
    token: str,
    *,
    tokens: list[str],
    index: int,
    parsed: dict[str, Any],
    normalize_browser_act_kind: Callable[[str], str],
    text_only_result: Callable[[str], Any],
    browser_usage_text: Callable[[], str],
    invalid_limit_result: Callable[[str, Callable[[str], Any]], Any],
    action: str,
) -> tuple[bool, int, Any | None]:
    if token == "--profile" and index + 1 < len(tokens):
        parsed["profile"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--transport" and index + 1 < len(tokens):
        transport = tokens[index + 1].strip().lower() or None
        if transport not in {"local", "proxy"}:
            return True, index, text_only_result(browser_usage_text())
        parsed["transport"] = transport
        return True, index + 2, None
    if token == "--tab" and index + 1 < len(tokens):
        parsed["tab_id"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--url" and index + 1 < len(tokens):
        parsed["url"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--path" and index + 1 < len(tokens):
        parsed["path"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--line" and index + 1 < len(tokens):
        try:
            parsed["line"] = int(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser open_legacy <url-or-ref-id> [line <n>]")
        return True, index + 2, None
    if token == "--id" and index + 1 < len(tokens):
        try:
            parsed["id"] = int(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser click_legacy <ref-id> <id>")
        return True, index + 2, None
    if token == "--level" and index + 1 < len(tokens):
        parsed["level"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--limit" and index + 1 < len(tokens):
        try:
            limit = int(tokens[index + 1])
        except ValueError:
            return True, index, invalid_limit_result(action, text_only_result)
        if limit <= 0:
            return True, index, invalid_limit_result(action, text_only_result)
        parsed["limit"] = limit
        return True, index + 2, None
    if token == "--outcome" and index + 1 < len(tokens):
        parsed["outcome"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--method" and index + 1 < len(tokens):
        parsed["method"] = tokens[index + 1].strip().upper() or None
        return True, index + 2, None
    if token == "--storage-kind" and index + 1 < len(tokens):
        parsed["storage_kind"] = tokens[index + 1].strip().lower() or None
        return True, index + 2, None
    if token == "--ref" and index + 1 < len(tokens):
        parsed["ref"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--start-ref" and index + 1 < len(tokens):
        parsed["start_ref"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--end-ref" and index + 1 < len(tokens):
        parsed["end_ref"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--kind" and index + 1 < len(tokens):
        kind = normalize_browser_act_kind(tokens[index + 1])
        parsed["kind"] = kind or None
        return True, index + 2, None
    if token == "--text" and index + 1 < len(tokens):
        parsed["text"] = tokens[index + 1]
        return True, index + 2, None
    if token == "--fn" and index + 1 < len(tokens):
        parsed["fn"] = tokens[index + 1]
        return True, index + 2, None
    if token == "--key" and index + 1 < len(tokens):
        parsed["key"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--cookies-json" and index + 1 < len(tokens):
        try:
            parsed_json = json.loads(tokens[index + 1])
        except json.JSONDecodeError:
            return True, index, text_only_result("Usage: /browser cookies set cookies-json '[{\"name\":\"session\",\"value\":\"abc\"}]'")
        parsed["cookies"] = [item for item in parsed_json if isinstance(item, dict)] if isinstance(parsed_json, list) else None
        return True, index + 2, None
    if token == "--items-json" and index + 1 < len(tokens):
        try:
            parsed_json = json.loads(tokens[index + 1])
        except json.JSONDecodeError:
            return True, index, text_only_result("Usage: /browser storage <local|session> set items-json '{\"theme\":\"dark\"}'")
        parsed["items"] = {str(k): v for k, v in parsed_json.items()} if isinstance(parsed_json, dict) else None
        return True, index + 2, None
    if token == "--domain" and index + 1 < len(tokens):
        parsed["cookie_domain"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--cookie-path" and index + 1 < len(tokens):
        parsed["cookie_path"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--same-site" and index + 1 < len(tokens):
        parsed["same_site"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--expires" and index + 1 < len(tokens):
        try:
            parsed["expires"] = float(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser cookies set <name> <value> [expires <unix-seconds>]")
        return True, index + 2, None
    if token == "--http-only":
        parsed["http_only"] = True
        return True, index + 1, None
    if token == "--secure":
        parsed["secure"] = True
        return True, index + 1, None
    if token == "--values" and index + 1 < len(tokens):
        parsed["values"] = [item.strip() for item in tokens[index + 1].split(",") if item.strip()]
        return True, index + 2, None
    if token == "--fields-json" and index + 1 < len(tokens):
        try:
            parsed_json = json.loads(tokens[index + 1])
        except json.JSONDecodeError:
            return True, index, text_only_result("Usage: /browser act fill fields-json '[{\"ref\":\"r1\",\"value\":\"x\"}]'")
        parsed["fields"] = [item for item in parsed_json if isinstance(item, dict)] if isinstance(parsed_json, list) else None
        return True, index + 2, None
    if token == "--time-ms" and index + 1 < len(tokens):
        try:
            parsed["time_ms"] = int(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser act wait time-ms <n>")
        return True, index + 2, None
    if token == "--width" and index + 1 < len(tokens):
        try:
            parsed["width"] = int(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser act resize <width> <height>")
        return True, index + 2, None
    if token == "--height" and index + 1 < len(tokens):
        try:
            parsed["height"] = int(tokens[index + 1])
        except ValueError:
            return True, index, text_only_result("Usage: /browser act resize <width> <height>")
        return True, index + 2, None
    if token == "--paths" and index + 1 < len(tokens):
        parsed["paths"] = [item.strip() for item in tokens[index + 1].split(",") if item.strip()]
        return True, index + 2, None
    if token == "--input-ref" and index + 1 < len(tokens):
        parsed["input_ref"] = tokens[index + 1].strip() or None
        return True, index + 2, None
    if token == "--accept":
        parsed["accept"] = True
        return True, index + 1, None
    if token == "--dismiss":
        parsed["accept"] = False
        return True, index + 1, None
    if token == "--prompt-text" and index + 1 < len(tokens):
        parsed["prompt_text"] = tokens[index + 1]
        return True, index + 2, None
    return False, index, None


def finalize_browser_command_defaults_impl(action: str, parsed: dict[str, Any], extras: list[str]) -> str:
    if action == "evaluate":
        action = "act"
        parsed["kind"] = "evaluate"
    if parsed["tab_id"] is None and extras and action in {"focus", "close"}:
        parsed["tab_id"] = extras[0].strip() or None
    if parsed["url"] is None and extras and action in {"open", "navigate"}:
        parsed["url"] = " ".join(extras).strip() or None
    if parsed["ref"] is None and extras and action == "highlight":
        parsed["ref"] = extras[0].strip() or None
    if parsed["path"] is None and extras and action == "trace_stop":
        parsed["path"] = " ".join(extras).strip() or None
    if action == "upload" and parsed["paths"] is None and extras:
        parsed["paths"] = [item.strip() for item in extras[0].split(",") if item.strip()]
    if action == "open_legacy":
        if parsed["ref"] is None and extras:
            parsed["ref"] = extras[0].strip() or None
        if parsed["line"] is None and len(extras) > 1:
            try:
                parsed["line"] = int(extras[1])
            except ValueError:
                parsed["line"] = None
    if action == "click_legacy":
        if parsed["ref"] is None and extras:
            parsed["ref"] = extras[0].strip() or None
        if parsed["id"] is None and len(extras) > 1:
            try:
                parsed["id"] = int(extras[1])
            except ValueError:
                parsed["id"] = None
    if action == "find_legacy":
        if parsed["ref"] is None and extras:
            parsed["ref"] = extras[0].strip() or None
        if parsed["text"] is None and len(extras) > 1:
            parsed["text"] = " ".join(extras[1:]).strip() or None
    return action


def finalize_cookies_action_impl(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
    *,
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    remaining = [item.strip() for item in extras if item.strip()]
    if not remaining:
        return action, parsed
    subcommand = remaining.pop(0).lower()
    if subcommand == "set":
        action = "cookies_set"
        if parsed["cookies"] is None:
            if len(remaining) < 2:
                return text_only_result("Usage: /browser cookies set <name> <value> [url <addr>|domain <host> cookie-path <path>]")
            parsed["cookies"] = [
                {
                    "name": remaining.pop(0),
                    "value": remaining.pop(0),
                    "url": parsed["url"],
                    "domain": parsed["cookie_domain"],
                    "path": parsed["cookie_path"],
                    "httpOnly": parsed["http_only"],
                    "secure": parsed["secure"],
                    "sameSite": parsed["same_site"],
                    "expires": parsed["expires"],
                }
            ]
        return action, parsed
    if subcommand == "clear":
        return "cookies_clear", parsed
    return text_only_result("Usage: /browser cookies [set <name> <value>|clear] [url <addr>]")


def finalize_storage_action_impl(
    parsed: dict[str, Any],
    extras: list[str],
    *,
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    remaining = [item.strip() for item in extras if item.strip()]
    if not remaining:
        return text_only_result("Usage: /browser storage <local|session> <get|set|clear> [key] [value]")
    parsed["storage_kind"] = parsed["storage_kind"] or remaining.pop(0).lower()
    if parsed["storage_kind"] not in {"local", "session"}:
        return text_only_result("Usage: /browser storage <local|session> <get|set|clear> [key] [value]")
    if not remaining:
        return text_only_result("Usage: /browser storage <local|session> <get|set|clear> [key] [value]")
    subcommand = remaining.pop(0).lower()
    if subcommand == "get":
        return "storage_get", parsed
    if subcommand == "set":
        action = "storage_set"
        if parsed["items"] is None:
            if len(remaining) < 2:
                return text_only_result("Usage: /browser storage <local|session> set <key> <value>")
            storage_key = remaining.pop(0)
            storage_value = " ".join(remaining).strip()
            if not storage_value:
                return text_only_result("Usage: /browser storage <local|session> set <key> <value>")
            parsed["items"] = {storage_key: storage_value}
        return action, parsed
    if subcommand == "clear":
        return "storage_clear", parsed
    return text_only_result("Usage: /browser storage <local|session> <get|set|clear> [key] [value]")


def finalize_act_action_impl(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
    *,
    normalize_browser_act_kind: Callable[[str], str],
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    remaining = [item.strip() for item in extras if item.strip()]
    if parsed["kind"] is None and remaining:
        parsed["kind"] = normalize_browser_act_kind(remaining.pop(0)) or None
    kind = parsed["kind"]
    if parsed["ref"] is None and kind in {"click", "double_click", "hover", "focus", "type", "clear", "check", "uncheck", "select", "scroll_into_view"} and remaining:
        parsed["ref"] = remaining.pop(0) or None
    if parsed["start_ref"] is None and kind == "drag" and remaining:
        parsed["start_ref"] = remaining.pop(0) or None
    if parsed["end_ref"] is None and kind == "drag" and remaining:
        parsed["end_ref"] = remaining.pop(0) or None
    if parsed["text"] is None and kind == "type" and remaining:
        parsed["text"] = " ".join(remaining).strip() or None
    if parsed["key"] is None and kind == "press" and remaining:
        parsed["key"] = remaining.pop(0) or None
    if parsed["values"] is None and kind == "select" and remaining:
        parsed["values"] = remaining
    if kind == "resize":
        if parsed["width"] is None and remaining:
            try:
                parsed["width"] = int(remaining.pop(0))
            except ValueError:
                return text_only_result("Usage: /browser act resize <width> <height>")
        if parsed["height"] is None and remaining:
            try:
                parsed["height"] = int(remaining.pop(0))
            except ValueError:
                return text_only_result("Usage: /browser act resize <width> <height>")
    if parsed["time_ms"] is None and kind == "wait" and remaining:
        try:
            parsed["time_ms"] = int(remaining[0])
        except ValueError:
            return text_only_result("Usage: /browser act wait time-ms <n>")
    if kind == "evaluate" and parsed["fn"] is None and remaining:
        if parsed["ref"] is None and len(remaining) > 1:
            parsed["ref"] = remaining.pop(0) or None
        parsed["fn"] = " ".join(remaining).strip() or None
    return action, parsed


def tool_call_arguments_impl(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": parsed["profile"],
        "transport": parsed["transport"],
        "tab_id": parsed["tab_id"],
        "url": parsed["url"],
        "path": parsed["path"],
        "line": parsed["line"],
        "id": parsed["id"],
        "level": parsed["level"],
        "limit": parsed["limit"],
        "outcome": parsed["outcome"],
        "method": parsed["method"],
        "storage_kind": parsed["storage_kind"],
        "ref": parsed["ref"],
        "start_ref": parsed["start_ref"],
        "end_ref": parsed["end_ref"],
        "kind": parsed["kind"],
        "text": parsed["text"],
        "fn": parsed["fn"],
        "key": parsed["key"],
        "cookies": parsed["cookies"],
        "items": parsed["items"],
        "values": parsed["values"],
        "fields": parsed["fields"],
        "time_ms": parsed["time_ms"],
        "width": parsed["width"],
        "height": parsed["height"],
        "paths": parsed["paths"],
        "input_ref": parsed["input_ref"],
        "accept": parsed["accept"],
        "prompt_text": parsed["prompt_text"],
    }
