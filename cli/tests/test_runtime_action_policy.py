from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from cli.agent_cli.gateway_core.actions import create_action_request
from cli.agent_cli.runtime_action_policy_runtime import (
    evaluate_apply_patch_action_policy,
    evaluate_browser_action_policy,
    evaluate_connector_action_policy,
    evaluate_exec_command_action_policy,
)


def _runtime(
    *,
    approval_policy: str = "on-request",
    sandbox_mode: str = "workspace-write",
    network_access_enabled: bool = True,
    cwd: str = ".",
):
    return SimpleNamespace(
        cwd=Path(cwd),
        runtime_policy=SimpleNamespace(
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            network_access_enabled=network_access_enabled,
        ),
        runtime_policy_status=lambda: {
            "approval_policy": approval_policy,
            "sandbox_mode": sandbox_mode,
            "network_access": "enabled" if network_access_enabled else "disabled",
        },
    )


def test_exec_action_policy_wraps_legacy_exec_policy_with_shared_contract() -> None:
    runtime = _runtime(approval_policy="never", sandbox_mode="workspace-write")

    state = evaluate_exec_command_action_policy(runtime, "pwd")

    assert state["action_policy_payload"]["action_kind"] == "exec_command"
    assert state["action_policy_payload"]["decision"] == "allowed"
    assert state["action_policy_payload"]["requirement"] == "skip"
    assert state["payload"]["action_policy"]["decision"] == "allowed"
    assert state["policy_decision"] == "allowed"


def test_exec_action_policy_records_requested_additional_permissions() -> None:
    runtime = _runtime(approval_policy="never", sandbox_mode="workspace-write")

    state = evaluate_exec_command_action_policy(
        runtime,
        "cat /tmp/ref",
        sandbox_permissions="with_additional_permissions",
        additional_permissions={"file_system": {"read": ["/tmp/ref"]}},
    )

    assert state["action_policy_payload"]["metadata"]["requested_sandbox_permissions"] == (
        "with_additional_permissions"
    )
    assert state["action_policy_payload"]["metadata"]["requested_additional_permissions"] == {
        "file_system": {"read": ["/tmp/ref"]}
    }


def test_exec_action_policy_prompts_for_pure_network_command() -> None:
    runtime = _runtime(approval_policy="on-request", sandbox_mode="workspace-write")

    state = evaluate_exec_command_action_policy(runtime, "curl -I https://example.com")

    assert state["action_policy_payload"]["decision"] == "requires_approval"
    assert state["action_policy_payload"]["requirement"] == "needs_approval"
    assert state["payload"]["reason_code"] == "exec.network.requires_approval"
    assert state["payload"]["network_access_enabled"] is True


def test_exec_action_policy_uses_requested_network_permission_in_classification() -> None:
    runtime = _runtime(
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        network_access_enabled=False,
    )

    state = evaluate_exec_command_action_policy(
        runtime,
        "python -V",
        sandbox_permissions="with_additional_permissions",
        additional_permissions={"network": {"enabled": True}},
    )

    assert state["action_policy_payload"]["decision"] == "requires_approval"
    assert state["action_policy_payload"]["requirement"] == "needs_approval"
    assert state["payload"]["reason_code"] == "exec.network.requires_approval"
    assert state["payload"]["requested_network_access"] is True
    assert state["action_policy_payload"]["metadata"]["requested_additional_permissions"] == {
        "network": {"enabled": True}
    }


def test_apply_patch_action_policy_wraps_patch_requirement_with_shared_contract() -> None:
    patch_text = """*** Begin Patch
*** Add File: note.txt
+hello
*** End Patch"""
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime(
            approval_policy="on-request",
            sandbox_mode="workspace-write",
            cwd=temp_dir,
        )

        state = evaluate_apply_patch_action_policy(
            runtime,
            patch_text=patch_text,
            workspace_root=Path(temp_dir),
        )

    assert state["action_policy_payload"]["action_kind"] == "apply_patch"
    assert state["action_policy_payload"]["decision"] == "requires_approval"
    assert state["action_policy_payload"]["requirement"] == "needs_approval"
    assert state["payload"]["action_policy"]["reason_code"] == "apply_patch_approval_required"


def test_browser_action_policy_maps_read_and_mutating_actions_into_shared_contract() -> None:
    read_state = evaluate_browser_action_policy(
        "browser.snapshot",
        payload={"target_id": "tab-1"},
    )
    risky_state = evaluate_browser_action_policy(
        "browser.act",
        payload={"kind": "click", "ref": "e4"},
    )

    assert read_state is not None
    assert read_state["action_policy_payload"]["decision"] == "allowed"
    assert read_state["action_policy_payload"]["requirement"] == "skip"
    assert read_state["approval_required"] is False

    assert risky_state is not None
    assert risky_state["action_policy_payload"]["decision"] == "requires_approval"
    assert risky_state["action_policy_payload"]["requirement"] == "needs_approval"
    assert risky_state["approval_required"] is True


def test_browser_create_action_request_persists_action_policy_metadata() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_action_policy",
        requested_by="tester",
        payload={"kind": "click", "ref": "e9"},
    )

    assert action.approval_required is True
    assert action.metadata["action_policy"]["action_kind"] == "browser"
    assert action.metadata["action_policy"]["decision"] == "requires_approval"


def test_connector_action_policy_reuses_shared_decision_vocabulary() -> None:
    allowed = evaluate_connector_action_policy(
        supports_actions=True,
        approval_policy="never",
    )
    approval_required = evaluate_connector_action_policy(
        supports_actions=True,
        approval_policy="on-request",
    )
    no_actions = evaluate_connector_action_policy(
        supports_actions=False,
        approval_policy="on-request",
    )

    assert allowed["approval_required"] is False
    assert allowed["action_policy_payload"]["decision"] == "allowed"
    assert allowed["payload"]["required"] is False

    assert approval_required["approval_required"] is True
    assert approval_required["action_policy_payload"]["requirement"] == "needs_approval"
    assert approval_required["payload"]["action_policy"]["action_kind"] == "connector"

    assert no_actions["approval_required"] is False
    assert no_actions["action_policy_payload"]["reason_code"] == "connector.no_actions.allowed"
