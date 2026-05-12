from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PERMISSION_MODES: tuple[str, ...] = (
    "default",
    "plan",
    "acceptEdits",
    "dontAsk",
    "bypassPermissions",
    "accept-edits",
    "dont-ask",
    "bypass-permissions",
)

_APPROVAL_POLICIES = ("never", "on-request", "on-failure", "unless-trusted")
_SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")
_PERMISSION_MODE_ALIASES: dict[str, str] = {
    "default": "default",
    "plan": "plan",
    "acceptedits": "acceptEdits",
    "accept-edits": "acceptEdits",
    "dontask": "dontAsk",
    "dont-ask": "dontAsk",
    "bypasspermissions": "bypassPermissions",
    "bypass-permissions": "bypassPermissions",
}

_PERMISSION_MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "default": {
        "approval_policy": "on-request",
        "sandbox_mode": "workspace-write",
        "network_access_enabled": True,
    },
    "plan": {
        "approval_policy": "on-request",
        "sandbox_mode": "read-only",
        "network_access_enabled": True,
    },
    "acceptEdits": {
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "network_access_enabled": True,
    },
    "dontAsk": {
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "network_access_enabled": True,
    },
    "bypassPermissions": {
        "approval_policy": "never",
        "sandbox_mode": "danger-full-access",
        "network_access_enabled": True,
    },
}


@dataclass(frozen=True)
class PermissionModeResolution:
    approval_policy: str | None
    sandbox_mode: str | None
    network_access_enabled: bool | None
    effective_permission_mode: str
    notices: tuple[str, ...]


def _normalize_token(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_approval_policy(value: str | None, *, default: str = "on-request") -> str:
    token = _normalize_token(value)
    if token == "untrusted":
        token = "unless-trusted"
    return token if token in _APPROVAL_POLICIES else default


def _normalize_sandbox_mode(value: str | None, *, default: str = "workspace-write") -> str:
    token = _normalize_token(value)
    return token if token in _SANDBOX_MODES else default


def _normalize_network_access(value: str | bool | None, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    token = _normalize_token(value)
    if token in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if token in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return default


def _explicit_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def normalize_permission_mode(value: str | None, *, default: str | None = "default") -> str | None:
    normalized_default = _PERMISSION_MODE_ALIASES.get(_normalize_token(default), default)
    token = _normalize_token(value)
    if not token:
        return normalized_default
    return _PERMISSION_MODE_ALIASES.get(token, normalized_default)


def permission_mode_defaults(permission_mode: str | None) -> dict[str, Any] | None:
    normalized = normalize_permission_mode(permission_mode, default=None)
    if normalized is None:
        return None
    defaults = _PERMISSION_MODE_DEFAULTS.get(normalized)
    if defaults is None:
        return None
    return dict(defaults)


def permission_mode_from_axes(
    *,
    approval_policy: str | None,
    sandbox_mode: str | None,
    network_access_enabled: str | bool | None,
) -> str:
    normalized_approval_policy = _normalize_approval_policy(approval_policy)
    normalized_sandbox_mode = _normalize_sandbox_mode(sandbox_mode)
    normalized_network_access_enabled = _normalize_network_access(network_access_enabled)
    for mode_name, defaults in _PERMISSION_MODE_DEFAULTS.items():
        if (
            normalized_approval_policy == str(defaults["approval_policy"])
            and normalized_sandbox_mode == str(defaults["sandbox_mode"])
            and normalized_network_access_enabled == bool(defaults["network_access_enabled"])
        ):
            return mode_name
    return "custom"


def status_with_permission_mode(status: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(status or {})
    network_access_value: str | bool | None = normalized.get("network_access_enabled")
    if network_access_value is None:
        network_access_value = normalized.get("network_access")
    normalized["permission_mode"] = permission_mode_from_axes(
        approval_policy=str(normalized.get("approval_policy") or "").strip() or None,
        sandbox_mode=str(normalized.get("sandbox_mode") or "").strip() or None,
        network_access_enabled=network_access_value,
    )
    return normalized


def resolve_permission_mode_updates(
    *,
    current_approval_policy: str | None,
    current_sandbox_mode: str | None,
    current_network_access_enabled: str | bool | None,
    permission_mode: str | None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
) -> PermissionModeResolution:
    current_approval = _normalize_approval_policy(current_approval_policy)
    current_sandbox = _normalize_sandbox_mode(current_sandbox_mode)
    current_network = _normalize_network_access(current_network_access_enabled)

    requested_mode_raw = _explicit_text(permission_mode)
    requested_mode = normalize_permission_mode(requested_mode_raw, default=None)

    approval_update: str | None = None
    sandbox_update: str | None = None
    network_update: bool | None = None

    target_approval = current_approval
    target_sandbox = current_sandbox
    target_network = current_network

    notices: list[str] = []
    conflicts: list[str] = []

    if requested_mode_raw is not None and requested_mode is None:
        supported = ", ".join(PERMISSION_MODES)
        notices.append(f"ignored invalid --permission-mode value: {requested_mode_raw!r}; supported: {supported}")

    requested_defaults = permission_mode_defaults(requested_mode)
    if requested_defaults is not None:
        target_approval = str(requested_defaults["approval_policy"])
        target_sandbox = str(requested_defaults["sandbox_mode"])
        target_network = bool(requested_defaults["network_access_enabled"])
        approval_update = target_approval
        sandbox_update = target_sandbox
        network_update = target_network

    explicit_approval = _explicit_text(approval_policy)
    if explicit_approval is not None:
        normalized_explicit_approval = _normalize_approval_policy(explicit_approval, default=current_approval)
        target_approval = normalized_explicit_approval
        approval_update = normalized_explicit_approval
        if requested_defaults is not None and normalized_explicit_approval != str(requested_defaults["approval_policy"]):
            conflicts.append(f"--approval-policy {explicit_approval}")

    explicit_sandbox = _explicit_text(sandbox_mode)
    if explicit_sandbox is not None:
        normalized_explicit_sandbox = _normalize_sandbox_mode(explicit_sandbox, default=current_sandbox)
        target_sandbox = normalized_explicit_sandbox
        sandbox_update = normalized_explicit_sandbox
        if requested_defaults is not None and normalized_explicit_sandbox != str(requested_defaults["sandbox_mode"]):
            conflicts.append(f"--sandbox-mode {explicit_sandbox}")

    explicit_network: str | bool | None
    if isinstance(network_access_enabled, bool):
        explicit_network = network_access_enabled
    else:
        explicit_network = _explicit_text(network_access_enabled)
    if explicit_network is not None:
        normalized_explicit_network = _normalize_network_access(explicit_network, default=current_network)
        target_network = normalized_explicit_network
        network_update = normalized_explicit_network
        if requested_defaults is not None and normalized_explicit_network != bool(requested_defaults["network_access_enabled"]):
            if isinstance(explicit_network, bool):
                rendered_network = "enabled" if explicit_network else "disabled"
            else:
                rendered_network = str(explicit_network)
            conflicts.append(f"--network-access {rendered_network}")

    if requested_mode is not None and conflicts:
        notices.append(
            "permission-mode "
            f"{requested_mode} overridden by explicit options ({', '.join(conflicts)}); explicit options take precedence."
        )

    effective_permission_mode = permission_mode_from_axes(
        approval_policy=target_approval,
        sandbox_mode=target_sandbox,
        network_access_enabled=target_network,
    )
    return PermissionModeResolution(
        approval_policy=approval_update,
        sandbox_mode=sandbox_update,
        network_access_enabled=network_update,
        effective_permission_mode=effective_permission_mode,
        notices=tuple(notices),
    )
