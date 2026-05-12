from __future__ import annotations

from cli.agent_cli.gateway_core.actions import create_action_request
from cli.agent_cli.gateway_core.approvals import create_approval_ticket
from cli.agent_cli.runtime import AgentCliRuntime

class _ClassificationAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "test",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("planner should not be used in browser gateway classification tests")

def test_create_action_request_classifies_browser_snapshot_as_read_only() -> None:
    action = create_action_request(
        action_type="browser.snapshot",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_read",
        requested_by="tester",
        payload={"target_id": "tab-1"},
    )

    assert action.action_family == "browser"
    assert action.action_class == "read_only"
    assert action.approval_policy == "never"
    assert action.audit_stage == "browser_read"
    assert action.approval_required is False
    assert action.metadata["browser"]["command"] == "snapshot"
    assert action.metadata["browser"]["action_class"] == "read_only"

def test_create_action_request_classifies_browser_wait_as_read_only() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_wait",
        requested_by="tester",
        payload={"kind": "wait", "time_ms": 500},
    )

    assert action.action_family == "browser"
    assert action.action_class == "read_only"
    assert action.approval_policy == "never"
    assert action.audit_stage == "browser_read"
    assert action.approval_required is False
    assert action.metadata["browser"]["action_kind"] == "wait"

def test_create_action_request_classifies_browser_fill_as_state_mutating() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_fill",
        requested_by="tester",
        payload={"kind": "fill", "ref": "e2", "text": "hello"},
    )

    assert action.action_family == "browser"
    assert action.action_class == "state_mutating"
    assert action.approval_policy == "always"
    assert action.audit_stage == "browser_state_change"
    assert action.approval_required is True
    assert action.metadata["browser"]["command"] == "act"
    assert action.metadata["browser"]["action_kind"] == "fill"

def test_create_action_request_serializes_browser_action_policy_metadata() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_policy_metadata",
        requested_by="tester",
        payload={"kind": "click", "ref": "e6"},
    )

    serialized = action.to_dict()
    action_policy = serialized["metadata"]["action_policy"]

    assert serialized["approval_required"] is True
    assert serialized["action_class"] == "external_side_effecting"
    assert serialized["approval_policy"] == "always"
    assert serialized["audit_stage"] == "browser_external_effect"
    assert action_policy["action_kind"] == "browser"
    assert action_policy["decision"] == "requires_approval"
    assert action_policy["requirement"] == "needs_approval"
    assert action_policy["metadata"]["action_class"] == "external_side_effecting"
    assert action_policy["metadata"]["audit_stage"] == "browser_external_effect"

def test_approval_ticket_preserves_browser_action_classification_metadata() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_click",
        requested_by="tester",
        payload={"kind": "click", "ref": "e4"},
        metadata={"workflow_name": "browser_mutate_after_approval"},
    )

    approval = create_approval_ticket(
        action,
        requested_by="workflow.browser",
        summary="Approve browser click",
    )

    assert action.action_class == "external_side_effecting"
    assert approval.metadata["source_action_family"] == "browser"
    assert approval.metadata["source_action_class"] == "external_side_effecting"
    assert approval.metadata["source_approval_policy"] == "always"
    assert approval.metadata["source_audit_stage"] == "browser_external_effect"
    assert approval.metadata["source_browser_action_kind"] == "click"
    assert approval.metadata["source_browser_command"] == "act"
    assert approval.metadata["browser"]["action_kind"] == "click"

def test_runtime_request_gateway_action_uses_browser_classification_defaults() -> None:
    runtime = AgentCliRuntime(agent=_ClassificationAgent())

    read_only = runtime.request_gateway_action(
        action_type="browser.snapshot",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        request_payload={"target_id": "tab-1"},
        requested_by="tester",
        trace_id="trace_runtime_browser_read",
    )
    risky = runtime.request_gateway_action(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        request_payload={"kind": "click", "ref": "e9"},
        requested_by="tester",
        trace_id="trace_runtime_browser_click",
        workflow_run_id="wf_browser_click",
    )

    assert read_only["action_request"].approval_required is False
    assert read_only["approval_ticket"] is None
    assert risky["action_request"].action_class == "external_side_effecting"
    assert risky["action_request"].approval_required is True
    assert risky["approval_ticket"] is not None

    diagnostics = runtime.list_approval_diagnostics(limit=5)

    assert diagnostics[0]["recommendation"]["action_family"] == "browser"
    assert diagnostics[0]["recommendation"]["action_class"] == "external_side_effecting"
    assert diagnostics[0]["recommendation"]["approval_policy"] == "always"
    assert diagnostics[0]["recommendation"]["audit_stage"] == "browser_external_effect"
    assert diagnostics[0]["recommendation"]["browser"]["action_kind"] == "click"
