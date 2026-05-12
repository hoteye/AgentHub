from __future__ import annotations

import shlex
from typing import Any, Callable, Dict

from . import browser_command_parsing_runtime


def normalize_browser_act_kind(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def parse_browser_command(
    arg_text: str,
    *,
    text_only_result: Callable[[str], Any],
    browser_usage_text: Callable[[], str],
    allowed_actions: set[str],
) -> tuple[str, dict[str, Any], list[str]] | Any:
    try:
        tokens = shlex.split(arg_text)
    except ValueError:
        tokens = str(arg_text or "").split()
    action = tokens[0].lower() if tokens else ""
    if action not in allowed_actions:
        return text_only_result(browser_usage_text())
    parsed = browser_command_parsing_runtime.build_initial_parsed_command()
    extras: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        handled, next_index, result = browser_command_parsing_runtime.parse_flag_token(
            token,
            tokens=tokens,
            index=index,
            parsed=parsed,
            normalize_browser_act_kind=normalize_browser_act_kind,
            text_only_result=text_only_result,
            browser_usage_text=browser_usage_text,
            invalid_limit_result=_invalid_limit_result,
            action=action,
        )
        if result is not None:
            return result
        if handled:
            index = next_index
            continue
        extras.append(token)
        index += 1
    return action, parsed, extras


def finalize_browser_command(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
    *,
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    action = browser_command_parsing_runtime.finalize_browser_command_defaults(action, parsed, extras)
    if action == "cookies":
        cookie_result = browser_command_parsing_runtime.finalize_cookies_action(
            action,
            parsed,
            extras,
            text_only_result=text_only_result,
        )
        if not isinstance(cookie_result, tuple):
            return cookie_result
        action, parsed = cookie_result
    if action == "storage":
        storage_result = browser_command_parsing_runtime.finalize_storage_action(
            parsed,
            extras,
            text_only_result=text_only_result,
        )
        if not isinstance(storage_result, tuple):
            return storage_result
        action, parsed = storage_result
    if action == "act":
        act_result = browser_command_parsing_runtime.finalize_act_action(
            action,
            parsed,
            extras,
            normalize_browser_act_kind=normalize_browser_act_kind,
            text_only_result=text_only_result,
        )
        if not isinstance(act_result, tuple):
            return act_result
        action, parsed = act_result
    return action, parsed


def compact_browser_arguments(parsed: dict[str, Any], *, compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]], action: str) -> dict[str, Any]:
    return compact_arguments({"action": action, **_tool_call_arguments(parsed)})


def browser_tool_result(
    runtime: Any,
    *,
    action: str,
    parsed: dict[str, Any],
    compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]],
    call_structured: Callable[..., Any],
    single_event_result: Callable[..., Any],
) -> Any:
    tool_kwargs = _tool_call_arguments(parsed)
    browser_arguments = compact_browser_arguments(parsed, compact_arguments=compact_arguments, action=action)
    structured = call_structured(
        runtime.tools,
        "browser_result",
        action,
        **tool_kwargs,
    )
    if structured is not None:
        return structured
    return single_event_result(
        f"Browser {action}.",
        runtime.tools.browser(action, **tool_kwargs),
        arguments=browser_arguments,
        tool_name="browser",
    )


def _tool_call_arguments(parsed: dict[str, Any]) -> dict[str, Any]:
    return browser_command_parsing_runtime.tool_call_arguments(parsed)


def _invalid_limit_result(action: str, text_only_result: Callable[[str], Any]) -> Any:
    if action == "console":
        return text_only_result("Usage: /browser console [level <info|warn|warning|error|debug>] [limit <n>]")
    return text_only_result("Usage: /browser errors|requests [limit <n>]")
