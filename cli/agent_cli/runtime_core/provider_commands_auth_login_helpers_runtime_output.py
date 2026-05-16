from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

CommandResult = tuple[str, list]


def command_result(lines: Iterable[str]) -> CommandResult:
    return ("\n".join(lines), [])


def auth_result(
    *,
    deps: Mapping[str, Any],
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    next_action: str,
    extra_lines: Iterable[str] = (),
) -> CommandResult:
    lines = deps["build_auth_status_lines_fn"](
        subcommand="login",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=next_action,
    )
    lines.extend(extra_lines)
    return command_result(lines)


def login_mode_result(
    *,
    deps: Mapping[str, Any],
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    mode: str,
    extra_lines: Iterable[str] = (),
    **hint_options: Any,
) -> CommandResult:
    next_action = deps["auth_command_hint_fn"](
        "login",
        provider_name=provider_name,
        mode=mode,
        **hint_options,
    )
    return auth_result(
        deps=deps,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=next_action,
        extra_lines=extra_lines,
    )


def provider_status_result(
    *,
    deps: Mapping[str, Any],
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    extra_lines: Iterable[str] = (),
) -> CommandResult:
    return auth_result(
        deps=deps,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=auth_status,
        next_action=deps["auth_command_hint_fn"]("status", provider_name=provider_name),
        extra_lines=extra_lines,
    )
