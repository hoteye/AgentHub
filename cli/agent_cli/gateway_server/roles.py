from __future__ import annotations

from typing import Iterable

GATEWAY_OPERATOR_ROLE = "operator"
GATEWAY_SYSTEM_ROLE = "system"
GATEWAY_WEBHOOK_ROLE = "webhook"
GATEWAY_PLUGIN_ROLE = "plugin"
GATEWAY_WORKER_ROLE = "worker"

GATEWAY_ROLES = (
    GATEWAY_OPERATOR_ROLE,
    GATEWAY_SYSTEM_ROLE,
    GATEWAY_WEBHOOK_ROLE,
    GATEWAY_PLUGIN_ROLE,
    GATEWAY_WORKER_ROLE,
)

GATEWAY_READ_SCOPE = "gateway.read"
GATEWAY_WRITE_SCOPE = "gateway.write"
APPROVALS_READ_SCOPE = "approvals.read"
APPROVALS_RESOLVE_SCOPE = "approvals.resolve"
BROWSER_READ_SCOPE = "browser.read"
BROWSER_WRITE_SCOPE = "browser.write"
GITHUB_READ_SCOPE = "github.read"
GITHUB_WRITE_SCOPE = "github.write"
PLUGINS_READ_SCOPE = "plugins.read"
PLUGINS_WRITE_SCOPE = "plugins.write"

GATEWAY_SCOPES = (
    GATEWAY_READ_SCOPE,
    GATEWAY_WRITE_SCOPE,
    APPROVALS_READ_SCOPE,
    APPROVALS_RESOLVE_SCOPE,
    BROWSER_READ_SCOPE,
    BROWSER_WRITE_SCOPE,
    GITHUB_READ_SCOPE,
    GITHUB_WRITE_SCOPE,
    PLUGINS_READ_SCOPE,
    PLUGINS_WRITE_SCOPE,
)

CLI_DEFAULT_OPERATOR_SCOPES: tuple[str, ...] = (
    GATEWAY_READ_SCOPE,
    GATEWAY_WRITE_SCOPE,
    APPROVALS_READ_SCOPE,
    APPROVALS_RESOLVE_SCOPE,
    BROWSER_READ_SCOPE,
    BROWSER_WRITE_SCOPE,
    GITHUB_READ_SCOPE,
    GITHUB_WRITE_SCOPE,
    PLUGINS_READ_SCOPE,
)

ROLE_DEFAULT_SCOPES: dict[str, tuple[str, ...]] = {
    GATEWAY_OPERATOR_ROLE: CLI_DEFAULT_OPERATOR_SCOPES,
    GATEWAY_SYSTEM_ROLE: CLI_DEFAULT_OPERATOR_SCOPES,
    GATEWAY_WEBHOOK_ROLE: (GITHUB_READ_SCOPE,),
    GATEWAY_PLUGIN_ROLE: (PLUGINS_READ_SCOPE,),
    GATEWAY_WORKER_ROLE: (
        GATEWAY_READ_SCOPE,
        GATEWAY_WRITE_SCOPE,
        BROWSER_READ_SCOPE,
        BROWSER_WRITE_SCOPE,
    ),
}

IMPLIED_SCOPES: dict[str, tuple[str, ...]] = {
    GATEWAY_WRITE_SCOPE: (GATEWAY_READ_SCOPE,),
    APPROVALS_RESOLVE_SCOPE: (APPROVALS_READ_SCOPE,),
    BROWSER_WRITE_SCOPE: (BROWSER_READ_SCOPE,),
    GITHUB_WRITE_SCOPE: (GITHUB_READ_SCOPE,),
    PLUGINS_WRITE_SCOPE: (PLUGINS_READ_SCOPE,),
}


def parse_gateway_role(role_raw: object) -> str | None:
    normalized = str(role_raw or "").strip()
    if normalized in GATEWAY_ROLES:
        return normalized
    return None


def normalize_gateway_roles(values: Iterable[str] | None = None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        role = parse_gateway_role(item)
        if not role or role in seen:
            continue
        seen.add(role)
        normalized.append(role)
    return normalized


def default_scopes_for_role(role: str) -> list[str]:
    parsed = parse_gateway_role(role)
    if not parsed:
        return []
    return list(ROLE_DEFAULT_SCOPES.get(parsed, ()))


def expand_gateway_scopes(scopes: Iterable[str] | None = None) -> list[str]:
    pending = [str(item).strip() for item in (scopes or []) if str(item).strip()]
    expanded: list[str] = []
    seen: set[str] = set()
    while pending:
        current = pending.pop(0)
        if current in seen:
            continue
        seen.add(current)
        expanded.append(current)
        pending.extend(IMPLIED_SCOPES.get(current, ()))
    return expanded


def resolve_scopes_for_roles(roles: Iterable[str] | None = None, explicit_scopes: Iterable[str] | None = None) -> list[str]:
    combined: list[str] = []
    for role in normalize_gateway_roles(roles):
        combined.extend(default_scopes_for_role(role))
    combined.extend(str(item).strip() for item in (explicit_scopes or []) if str(item).strip())
    return expand_gateway_scopes(combined)


def resolve_allowed_roles_for_method(method: str) -> tuple[str, ...]:
    normalized = str(method or "").strip()
    if not normalized:
        return ()
    if normalized.startswith("connect."):
        return GATEWAY_ROLES
    if normalized == "github.webhook.ingest":
        return (
            GATEWAY_OPERATOR_ROLE,
            GATEWAY_SYSTEM_ROLE,
            GATEWAY_WEBHOOK_ROLE,
        )
    if normalized.startswith("plugins."):
        return (
            GATEWAY_OPERATOR_ROLE,
            GATEWAY_SYSTEM_ROLE,
            GATEWAY_PLUGIN_ROLE,
        )
    if normalized.startswith("browser.") or normalized.startswith("workflows."):
        return (
            GATEWAY_OPERATOR_ROLE,
            GATEWAY_SYSTEM_ROLE,
            GATEWAY_WORKER_ROLE,
        )
    return (
        GATEWAY_OPERATOR_ROLE,
        GATEWAY_SYSTEM_ROLE,
    )


def is_role_authorized_for_method(role: str, method: str) -> bool:
    parsed = parse_gateway_role(role)
    if not parsed:
        return False
    return parsed in resolve_allowed_roles_for_method(method)
