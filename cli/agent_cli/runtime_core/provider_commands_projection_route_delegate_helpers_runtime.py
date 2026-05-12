from __future__ import annotations

from typing import Any


def route_overview_lines(status: dict[str, Any], *, route_overrides: Any) -> list[str]:
    lines = ["session route status"]
    for route_name in ("policy_helper", "tool_followup", "final_synthesis"):
        lines.append(f"route_{route_name}={status.get(f'route_{route_name}') or '-'}")
    lines.append(
        f"route_override_count={len(route_overrides)}"
        if isinstance(route_overrides, dict)
        else "route_override_count=0"
    )
    return lines


def route_current_lines(
    *,
    route_name: str,
    route_status: str,
    override_active: str,
) -> list[str]:
    return [
        f"route={route_name}",
        f"route_status={route_status}",
        f"override_active={override_active}",
    ]


def route_update_lines(
    *,
    route_name: str,
    route_status: str,
    clear: bool,
) -> list[str]:
    headline = (
        f"cleared session route override route={route_name}"
        if clear
        else f"updated session route override route={route_name}"
    )
    return [
        headline,
        f"route_status={route_status}",
        f"override_active={'false' if clear else 'true'}",
    ]


def delegate_overview_lines(status: dict[str, Any], *, delegate_overrides: Any) -> list[str]:
    lines = ["session delegation status"]
    for role_name in ("subagent", "teammate"):
        lines.append(f"delegate_{role_name}={status.get(f'delegate_{role_name}') or '-'}")
    lines.append(
        f"delegate_override_count={len(delegate_overrides)}"
        if isinstance(delegate_overrides, dict)
        else "delegate_override_count=0"
    )
    return lines


def delegate_current_lines(
    *,
    role_name: str,
    delegate_status: str,
    override_active: str,
) -> list[str]:
    return [
        f"role={role_name}",
        f"delegate_status={delegate_status}",
        f"override_active={override_active}",
    ]


def delegate_update_lines(
    *,
    role_name: str,
    delegate_status: str,
    clear: bool,
) -> list[str]:
    headline = (
        f"cleared session delegation override role={role_name}"
        if clear
        else f"updated session delegation override role={role_name}"
    )
    return [
        headline,
        f"delegate_status={delegate_status}",
        f"override_active={'false' if clear else 'true'}",
    ]


__all__ = [
    "delegate_current_lines",
    "delegate_overview_lines",
    "delegate_update_lines",
    "route_current_lines",
    "route_overview_lines",
    "route_update_lines",
]
