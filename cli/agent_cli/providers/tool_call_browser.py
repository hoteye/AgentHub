from __future__ import annotations

import json
from typing import Any, Callable, Dict


def browser_tool_call_command(
    arguments: Dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
) -> str | None:
    action = str(arguments.get("action") or "").strip()
    if not action:
        return None
    if action == "cookies_get":
        command = "/browser cookies"
        tab_id = str(arguments.get("tab") or arguments.get("tab_id") or "").strip()
        if tab_id:
            command += f" --tab {quote_arg_fn(tab_id)}"
        profile = str(arguments.get("profile") or "").strip()
        if profile:
            command += f" --profile {quote_arg_fn(profile)}"
        return command
    if action == "cookies_clear":
        command = "/browser cookies clear"
        tab_id = str(arguments.get("tab") or arguments.get("tab_id") or "").strip()
        if tab_id:
            command += f" --tab {quote_arg_fn(tab_id)}"
        profile = str(arguments.get("profile") or "").strip()
        if profile:
            command += f" --profile {quote_arg_fn(profile)}"
        return command
    if action == "cookies_set":
        command = "/browser cookies set"
        tab_id = str(arguments.get("tab") or arguments.get("tab_id") or "").strip()
        profile = str(arguments.get("profile") or "").strip()
        cookies = arguments.get("cookies")
        cookie_list = [item for item in cookies if isinstance(item, dict)] if isinstance(cookies, list) else []
        first_cookie = cookie_list[0] if cookie_list else {}
        name_value = str(first_cookie.get("name") or "").strip()
        cookie_value = str(first_cookie.get("value") or "")
        if name_value and cookie_value:
            command += f" {quote_arg_fn(name_value)} {quote_arg_fn(cookie_value)}"
        elif cookie_list:
            command += f" --cookies-json {quote_arg_fn(json.dumps(cookie_list, ensure_ascii=True))}"
        else:
            return None
        if tab_id:
            command += f" --tab {quote_arg_fn(tab_id)}"
        if profile:
            command += f" --profile {quote_arg_fn(profile)}"
        cookie_url = str(first_cookie.get("url") or arguments.get("url") or "").strip()
        if cookie_url:
            command += f" --url {quote_arg_fn(cookie_url)}"
        cookie_domain = str(first_cookie.get("domain") or "").strip()
        if cookie_domain:
            command += f" --domain {quote_arg_fn(cookie_domain)}"
        cookie_path = str(first_cookie.get("path") or "").strip()
        if cookie_path:
            command += f" --cookie-path {quote_arg_fn(cookie_path)}"
        if first_cookie.get("httpOnly") is True:
            command += " --http-only"
        if first_cookie.get("secure") is True:
            command += " --secure"
        same_site = str(first_cookie.get("sameSite") or "").strip()
        if same_site:
            command += f" --same-site {quote_arg_fn(same_site)}"
        expires = first_cookie.get("expires")
        if expires is not None:
            command += f" --expires {quote_arg_fn(expires)}"
        return command
    if action in {"storage_get", "storage_clear", "storage_set"}:
        storage_kind = str(arguments.get("storage_kind") or "").strip().lower()
        if storage_kind not in {"local", "session"}:
            return None
        verb = "get" if action == "storage_get" else ("clear" if action == "storage_clear" else "set")
        command = f"/browser storage {quote_arg_fn(storage_kind)} {verb}"
        tab_id = str(arguments.get("tab") or arguments.get("tab_id") or "").strip()
        if tab_id:
            command += f" --tab {quote_arg_fn(tab_id)}"
        profile = str(arguments.get("profile") or "").strip()
        if profile:
            command += f" --profile {quote_arg_fn(profile)}"
        if action == "storage_set":
            items = arguments.get("items")
            if isinstance(items, dict) and items:
                item_entries = [(str(key).strip(), str(value)) for key, value in items.items() if str(key).strip()]
                if len(item_entries) == 1:
                    key_name, key_value = item_entries[0]
                    command += f" {quote_arg_fn(key_name)} {quote_arg_fn(key_value)}"
                else:
                    command += f" --items-json {quote_arg_fn(json.dumps({k: v for k, v in item_entries}, ensure_ascii=True))}"
            else:
                return None
        return command
    command = f"/browser {quote_arg_fn(action)}"
    profile = str(arguments.get("profile") or "").strip()
    if profile:
        command += f" --profile {quote_arg_fn(profile)}"
    transport = str(arguments.get("transport") or "").strip().lower()
    if transport:
        command += f" --transport {quote_arg_fn(transport)}"
    tab_id = str(arguments.get("tab") or arguments.get("tab_id") or "").strip()
    if tab_id:
        command += f" --tab {quote_arg_fn(tab_id)}"
    url = str(arguments.get("url") or "").strip()
    if url:
        command += f" --url {quote_arg_fn(url)}"
    path = str(arguments.get("path") or "").strip()
    if path:
        command += f" --path {quote_arg_fn(path)}"
    level = str(arguments.get("level") or "").strip()
    if level:
        command += f" --level {quote_arg_fn(level)}"
    limit = arguments.get("limit")
    if limit is not None:
        command += f" --limit {quote_arg_fn(limit)}"
    outcome = str(arguments.get("outcome") or "").strip()
    if outcome:
        command += f" --outcome {quote_arg_fn(outcome)}"
    method = str(arguments.get("method") or "").strip()
    if method:
        command += f" --method {quote_arg_fn(method)}"
    ref = str(arguments.get("ref") or "").strip()
    if ref:
        command += f" --ref {quote_arg_fn(ref)}"
    start_ref = str(arguments.get("start_ref") or "").strip()
    if start_ref:
        command += f" --start-ref {quote_arg_fn(start_ref)}"
    end_ref = str(arguments.get("end_ref") or "").strip()
    if end_ref:
        command += f" --end-ref {quote_arg_fn(end_ref)}"
    kind = str(arguments.get("kind") or "").strip()
    if kind:
        command += f" --kind {quote_arg_fn(kind)}"
    text = str(arguments.get("text") or "").strip()
    if text:
        command += f" --text {quote_arg_fn(text)}"
    fn = str(arguments.get("fn") or "").strip()
    if fn:
        command += f" --fn {quote_arg_fn(fn)}"
    key = str(arguments.get("key") or "").strip()
    if key:
        command += f" --key {quote_arg_fn(key)}"
    values = arguments.get("values")
    if isinstance(values, (list, tuple)):
        normalized_values = ",".join(str(item).strip() for item in values if str(item).strip())
        if normalized_values:
            command += f" --values {quote_arg_fn(normalized_values)}"
    fields = arguments.get("fields")
    if isinstance(fields, (list, tuple)) and fields:
        command += f" --fields-json {quote_arg_fn(json.dumps(list(fields), ensure_ascii=True))}"
    time_ms = arguments.get("time_ms")
    if time_ms is not None:
        command += f" --time-ms {quote_arg_fn(time_ms)}"
    width = arguments.get("width")
    if width is not None:
        command += f" --width {quote_arg_fn(width)}"
    height = arguments.get("height")
    if height is not None:
        command += f" --height {quote_arg_fn(height)}"
    paths = arguments.get("paths")
    if isinstance(paths, (list, tuple)):
        normalized_paths = ",".join(str(item).strip() for item in paths if str(item).strip())
        if normalized_paths:
            command += f" --paths {quote_arg_fn(normalized_paths)}"
    input_ref = str(arguments.get("input_ref") or "").strip()
    if input_ref:
        command += f" --input-ref {quote_arg_fn(input_ref)}"
    if "accept" in arguments and arguments.get("accept") is not None:
        command += " --accept" if bool(arguments.get("accept")) else " --dismiss"
    prompt_text = str(arguments.get("prompt_text") or "").strip()
    if prompt_text:
        command += f" --prompt-text {quote_arg_fn(prompt_text)}"
    return command
