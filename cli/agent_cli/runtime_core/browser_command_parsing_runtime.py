from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import browser_command_parsing_helpers_runtime as _helpers


def build_initial_parsed_command() -> dict[str, Any]:
    return {
        "profile": None,
        "transport": None,
        "tab_id": None,
        "url": None,
        "path": None,
        "line": None,
        "id": None,
        "level": None,
        "limit": None,
        "outcome": None,
        "method": None,
        "storage_kind": None,
        "ref": None,
        "start_ref": None,
        "end_ref": None,
        "kind": None,
        "text": None,
        "fn": None,
        "key": None,
        "cookies": None,
        "items": None,
        "values": None,
        "fields": None,
        "time_ms": None,
        "width": None,
        "height": None,
        "cookie_domain": None,
        "cookie_path": None,
        "same_site": None,
        "expires": None,
        "http_only": False,
        "secure": False,
        "paths": None,
        "input_ref": None,
        "accept": None,
        "prompt_text": None,
    }


def parse_flag_token(
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
    return _helpers.parse_flag_token_impl(
        token,
        tokens=tokens,
        index=index,
        parsed=parsed,
        normalize_browser_act_kind=normalize_browser_act_kind,
        text_only_result=text_only_result,
        browser_usage_text=browser_usage_text,
        invalid_limit_result=invalid_limit_result,
        action=action,
    )


def finalize_browser_command_defaults(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
) -> str:
    return _helpers.finalize_browser_command_defaults_impl(action, parsed, extras)


def finalize_cookies_action(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
    *,
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    return _helpers.finalize_cookies_action_impl(
        action,
        parsed,
        extras,
        text_only_result=text_only_result,
    )


def finalize_storage_action(
    parsed: dict[str, Any],
    extras: list[str],
    *,
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    return _helpers.finalize_storage_action_impl(
        parsed,
        extras,
        text_only_result=text_only_result,
    )


def finalize_act_action(
    action: str,
    parsed: dict[str, Any],
    extras: list[str],
    *,
    normalize_browser_act_kind: Callable[[str], str],
    text_only_result: Callable[[str], Any],
) -> tuple[str, dict[str, Any]] | Any:
    return _helpers.finalize_act_action_impl(
        action,
        parsed,
        extras,
        normalize_browser_act_kind=normalize_browser_act_kind,
        text_only_result=text_only_result,
    )


def tool_call_arguments(parsed: dict[str, Any]) -> dict[str, Any]:
    return _helpers.tool_call_arguments_impl(parsed)
