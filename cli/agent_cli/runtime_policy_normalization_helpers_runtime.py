from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_permission_mode import (
    permission_mode_from_axes,
    resolve_permission_mode_updates,
)


APPROVAL_POLICIES = ("never", "on-request", "on-failure", "untrusted", "unless-trusted")
SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")
WEB_SEARCH_MODES = ("disabled", "cached", "live")


def normalize_token(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_approval_policy(value: str | None, *, default: str = "on-request") -> str:
    token = normalize_token(value)
    return token if token in APPROVAL_POLICIES else default


def normalize_sandbox_mode(value: str | None, *, default: str = "workspace-write") -> str:
    token = normalize_token(value)
    return token if token in SANDBOX_MODES else default


def default_web_search_mode_for_sandbox(sandbox_mode: str | None) -> str:
    normalized_sandbox = normalize_sandbox_mode(sandbox_mode)
    return "live" if normalized_sandbox == "danger-full-access" else "cached"


def normalize_web_search_mode(
    value: str | None,
    *,
    default: str | None = None,
    sandbox_mode: str | None = None,
) -> str:
    token = normalize_token(value)
    if token in WEB_SEARCH_MODES:
        return token
    fallback = str(default or "").strip().lower() or default_web_search_mode_for_sandbox(sandbox_mode)
    return fallback if fallback in WEB_SEARCH_MODES else default_web_search_mode_for_sandbox(sandbox_mode)


def normalize_network_access(value: str | bool | None, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    token = normalize_token(value)
    if token in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if token in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return default


def optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    token = normalize_token(value if value is not None else "")
    if token in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if token in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return None


def network_access_label(enabled: bool) -> str:
    return "enabled" if enabled else "disabled"


def permission_mode_label(
    *,
    approval_policy: str | None,
    sandbox_mode: str | None,
    network_access_enabled: str | bool | None,
) -> str:
    return permission_mode_from_axes(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        network_access_enabled=network_access_enabled,
    )


def normalized_runtime_policy_values(
    *,
    permission_mode: str | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    web_search_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
) -> dict[str, Any]:
    resolution = resolve_permission_mode_updates(
        current_approval_policy=approval_policy,
        current_sandbox_mode=sandbox_mode,
        current_network_access_enabled=network_access_enabled,
        permission_mode=permission_mode,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        network_access_enabled=network_access_enabled,
    )
    resolved_sandbox_mode = (
        str(resolution.sandbox_mode)
        if resolution.sandbox_mode is not None
        else normalize_sandbox_mode(sandbox_mode)
    )
    return {
        "approval_policy": (
            str(resolution.approval_policy)
            if resolution.approval_policy is not None
            else normalize_approval_policy(approval_policy)
        ),
        "sandbox_mode": resolved_sandbox_mode,
        "web_search_mode": normalize_web_search_mode(
            web_search_mode,
            sandbox_mode=resolved_sandbox_mode,
        ),
        "network_access_enabled": (
            bool(resolution.network_access_enabled)
            if resolution.network_access_enabled is not None
            else normalize_network_access(network_access_enabled)
        ),
    }


def updated_runtime_policy_values(
    *,
    current_approval_policy: str,
    current_sandbox_mode: str,
    current_web_search_mode: str,
    current_network_access_enabled: bool,
    permission_mode: str | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    web_search_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
) -> dict[str, Any]:
    resolution = resolve_permission_mode_updates(
        current_approval_policy=current_approval_policy,
        current_sandbox_mode=current_sandbox_mode,
        current_network_access_enabled=current_network_access_enabled,
        permission_mode=permission_mode,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        network_access_enabled=network_access_enabled,
    )
    next_sandbox_mode = (
        str(resolution.sandbox_mode)
        if resolution.sandbox_mode is not None
        else current_sandbox_mode
    )
    if web_search_mode is not None:
        next_web_search_mode = normalize_web_search_mode(
            web_search_mode,
            default=current_web_search_mode,
            sandbox_mode=next_sandbox_mode,
        )
    elif resolution.sandbox_mode is not None or permission_mode is not None:
        current_web_search_mode_normalized = normalize_web_search_mode(
            current_web_search_mode,
            sandbox_mode=current_sandbox_mode,
        )
        next_web_search_mode = (
            "disabled"
            if current_web_search_mode_normalized == "disabled"
            else default_web_search_mode_for_sandbox(next_sandbox_mode)
        )
    else:
        next_web_search_mode = current_web_search_mode
    return {
        "approval_policy": (
            str(resolution.approval_policy)
            if resolution.approval_policy is not None
            else current_approval_policy
        ),
        "sandbox_mode": next_sandbox_mode,
        "web_search_mode": next_web_search_mode,
        "network_access_enabled": (
            bool(resolution.network_access_enabled)
            if resolution.network_access_enabled is not None
            else current_network_access_enabled
        ),
    }
