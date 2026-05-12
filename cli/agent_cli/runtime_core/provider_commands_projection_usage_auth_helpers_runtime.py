from __future__ import annotations

from typing import Callable


def provider_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return "\n".join(
        [
            f"Usage: {surface_usage_text_fn('provider')}",
            "Advanced: /provider [name] --write <session|user|project> [--verbose] [--probe]",
        ]
    )


def model_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return "\n".join(
        [
            f"Usage: {surface_usage_text_fn('model')}",
            "Advanced: /model [name] [--reasoning-effort <low|medium|high|xhigh|default>] [--write <session|user|project>]",
        ]
    )


def connect_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return f"Usage: {surface_usage_text_fn('connect')}"


def auth_usage_text(*, surface_usage_text_fn: Callable[[str], str]) -> str:
    return f"Usage: {surface_usage_text_fn('auth')}"


def slash_command_text(name: str, *parts: str) -> str:
    rendered = [f"/{str(name or '').strip().lstrip('/')}".rstrip()]
    rendered.extend(str(part).strip() for part in parts if str(part).strip())
    return " ".join(rendered)


def auth_command_hint(
    action: str,
    *,
    provider_name: str = "",
    mode: str = "",
    poll: bool = False,
    auth_code: str = "",
    state: str = "",
    auto: bool = False,
    daemon: str = "",
    managed: bool = False,
    slash_command_text_fn: Callable[..., str],
) -> str:
    parts: list[str] = [action]
    if provider_name:
        parts.extend(("provider", provider_name))
    if mode:
        parts.extend(("mode", mode))
    if poll:
        parts.append("poll")
    if auth_code:
        parts.extend(("auth-code", auth_code))
    if state:
        parts.extend(("state", state))
    if auto:
        parts.append("auto")
    if daemon:
        parts.extend(("daemon", daemon))
    if managed:
        parts.append("managed")
    return slash_command_text_fn("auth", *parts)


def build_auth_status_lines(
    *,
    subcommand: str,
    provider_name: str,
    auth_mode: str,
    auth_status: str,
    next_action: str,
) -> list[str]:
    return [
        f"auth {subcommand}",
        f"provider_name={provider_name}",
        f"auth_mode={auth_mode}",
        f"auth_status={auth_status}",
        f"next_action={next_action}",
    ]


__all__ = [
    "auth_command_hint",
    "auth_usage_text",
    "build_auth_status_lines",
    "connect_usage_text",
    "model_usage_text",
    "provider_usage_text",
    "slash_command_text",
]
