from __future__ import annotations

from cli.agent_cli.runtime_permission_mode import (
    permission_mode_defaults,
    permission_mode_from_axes,
    resolve_permission_mode_updates,
    status_with_permission_mode,
)
from cli.agent_cli.runtime_policy import RuntimePolicy


def test_permission_mode_defaults_map_expected_axes() -> None:
    assert permission_mode_defaults("default") == {
        "approval_policy": "on-request",
        "sandbox_mode": "workspace-write",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("plan") == {
        "approval_policy": "on-request",
        "sandbox_mode": "read-only",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("acceptEdits") == {
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("accept-edits") == {
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("dontAsk") == {
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("dont-ask") == {
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("bypassPermissions") == {
        "approval_policy": "never",
        "sandbox_mode": "danger-full-access",
        "network_access_enabled": True,
    }
    assert permission_mode_defaults("bypass-permissions") == {
        "approval_policy": "never",
        "sandbox_mode": "danger-full-access",
        "network_access_enabled": True,
    }


def test_permission_mode_from_axes_returns_custom_for_non_profile() -> None:
    assert permission_mode_from_axes(
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        network_access_enabled=True,
    ) == "default"
    assert permission_mode_from_axes(
        approval_policy="on-request",
        sandbox_mode="read-only",
        network_access_enabled=True,
    ) == "plan"
    assert permission_mode_from_axes(
        approval_policy="never",
        sandbox_mode="workspace-write",
        network_access_enabled=True,
    ) == "acceptEdits"
    assert permission_mode_from_axes(
        approval_policy="never",
        sandbox_mode="read-only",
        network_access_enabled=True,
    ) == "dontAsk"
    assert permission_mode_from_axes(
        approval_policy="never",
        sandbox_mode="danger-full-access",
        network_access_enabled=True,
    ) == "bypassPermissions"
    assert permission_mode_from_axes(
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        network_access_enabled=False,
    ) == "custom"


def test_status_with_permission_mode_uses_existing_status_axes() -> None:
    status = status_with_permission_mode(
        {
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access": "enabled",
        }
    )
    assert status["permission_mode"] == "default"


def test_resolve_permission_mode_updates_uses_mode_defaults() -> None:
    resolution = resolve_permission_mode_updates(
        current_approval_policy="never",
        current_sandbox_mode="read-only",
        current_network_access_enabled=False,
        permission_mode="default",
    )
    assert resolution.approval_policy == "on-request"
    assert resolution.sandbox_mode == "workspace-write"
    assert resolution.network_access_enabled is True
    assert resolution.effective_permission_mode == "default"
    assert resolution.notices == ()


def test_resolve_permission_mode_updates_prefers_explicit_conflicts() -> None:
    resolution = resolve_permission_mode_updates(
        current_approval_policy="on-request",
        current_sandbox_mode="workspace-write",
        current_network_access_enabled=True,
        permission_mode="plan",
        sandbox_mode="workspace-write",
        network_access_enabled="disabled",
    )
    assert resolution.approval_policy == "on-request"
    assert resolution.sandbox_mode == "workspace-write"
    assert resolution.network_access_enabled is False
    assert resolution.effective_permission_mode == "custom"
    assert len(resolution.notices) == 1
    assert "explicit options take precedence" in resolution.notices[0]


def test_resolve_permission_mode_updates_accepts_kebab_case_aliases() -> None:
    resolution = resolve_permission_mode_updates(
        current_approval_policy="on-request",
        current_sandbox_mode="workspace-write",
        current_network_access_enabled=True,
        permission_mode="bypass-permissions",
    )
    assert resolution.approval_policy == "never"
    assert resolution.sandbox_mode == "danger-full-access"
    assert resolution.network_access_enabled is True
    assert resolution.effective_permission_mode == "bypassPermissions"
    assert resolution.notices == ()


def test_resolve_permission_mode_updates_reports_invalid_mode() -> None:
    resolution = resolve_permission_mode_updates(
        current_approval_policy="on-request",
        current_sandbox_mode="workspace-write",
        current_network_access_enabled=True,
        permission_mode="invalid-mode",
    )
    assert resolution.approval_policy is None
    assert resolution.sandbox_mode is None
    assert resolution.network_access_enabled is None
    assert resolution.effective_permission_mode == "default"
    assert len(resolution.notices) == 1
    assert "ignored invalid --permission-mode value" in resolution.notices[0]


def test_runtime_policy_normalized_applies_permission_mode_defaults() -> None:
    policy = RuntimePolicy.normalized(permission_mode="plan")
    assert policy.approval_policy == "on-request"
    assert policy.sandbox_mode == "read-only"
    assert policy.network_access_enabled is True
    assert policy.permission_mode() == "plan"


def test_runtime_policy_with_updates_prefers_explicit_axes_over_mode() -> None:
    policy = RuntimePolicy.normalized(permission_mode="default")
    updated = policy.with_updates(permission_mode="plan", sandbox_mode="danger-full-access")
    assert updated.approval_policy == "on-request"
    assert updated.sandbox_mode == "danger-full-access"
    assert updated.network_access_enabled is True
    assert updated.permission_mode() == "custom"


def test_runtime_policy_normalized_accepts_camel_case_permission_mode() -> None:
    policy = RuntimePolicy.normalized(permission_mode="acceptEdits")
    assert policy.approval_policy == "never"
    assert policy.sandbox_mode == "workspace-write"
    assert policy.network_access_enabled is True
    assert policy.permission_mode() == "acceptEdits"
