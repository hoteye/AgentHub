from __future__ import annotations

from cli.agent_cli.gateway_core import (
    ActionRequest,
    ApprovalTicket,
    AuditRecord,
    ConnectorRegistration,
    GatewayEvent,
    PolicyRegistration,
    TriggerRegistration,
    WorkflowRun,
    create_gateway_event,
    gateway_event_from_dict,
)

def test_gateway_event_round_trip_uses_contract_field_names() -> None:
    event = create_gateway_event(
        event_type="policy.audit.created",
        source_kind="webhook",
        source_id="webhook:psbc",
        connector_key="psbc_webhook",
        payload={"case_id": "c1"},
        metadata={"headers": {"x-test": "1"}},
        plugin_name="psbc_policy",
    )

    restored = gateway_event_from_dict(event.to_dict())

    assert isinstance(restored, GatewayEvent)
    assert restored.event_type == "policy.audit.created"
    assert restored.connector_key == "psbc_webhook"
    assert restored.payload == {"case_id": "c1"}
    assert restored.metadata == {"headers": {"x-test": "1"}}

def test_gateway_contract_models_expose_expected_minimum_fields() -> None:
    connector = ConnectorRegistration(
        connector_key="webhook_demo",
        plugin_name="demo_plugin",
        display_name="Demo Webhook",
        version="1",
        connector_kind="inbound",
        event_types=["demo.event"],
        action_types=[],
    )
    trigger = TriggerRegistration(
        trigger_key="demo_trigger",
        plugin_name="demo_plugin",
        trigger_kind="event",
        connector_key="webhook_demo",
        event_types=["demo.event"],
        workflow_name="handle_demo_event",
    )
    policy = PolicyRegistration(
        policy_key="demo_policy",
        plugin_name="demo_plugin",
        display_name="Demo Approval Policy",
        version="1",
        policy_kind="approval",
        applies_to=["action.request"],
    )
    action = ActionRequest(
        action_id="action_1",
        action_type="connector.call",
        connector_key="webhook_demo",
        plugin_name="demo_plugin",
        trace_id="trace_1",
        requested_at="2026-03-26T10:00:00+00:00",
        requested_by="system",
        approval_required=True,
        action_family="browser",
        action_class="read_only",
        approval_policy="never",
        audit_stage="browser_read",
    )
    approval = ApprovalTicket(
        approval_id="approval_1",
        action_id="action_1",
        trace_id="trace_1",
        status="pending",
        requested_at="2026-03-26T10:00:00+00:00",
        requested_by="system",
    )
    audit = AuditRecord(
        audit_id="audit_1",
        trace_id="trace_1",
        stage="ingress",
        created_at="2026-03-26T10:00:00+00:00",
        status="ok",
        summary="event received",
    )
    workflow = WorkflowRun(
        workflow_run_id="wf_1",
        workflow_name="handle_demo_event",
        plugin_name="demo_plugin",
        trace_id="trace_1",
        status="pending",
        started_at="2026-03-26T10:00:00+00:00",
        updated_at="2026-03-26T10:00:00+00:00",
    )

    assert connector.to_dict()["connector_key"] == "webhook_demo"
    assert trigger.to_dict()["workflow_name"] == "handle_demo_event"
    assert policy.to_dict()["policy_kind"] == "approval"
    assert action.to_dict()["approval_required"] is True
    assert action.to_dict()["action_family"] == "browser"
    assert action.to_dict()["action_class"] == "read_only"
    assert action.to_dict()["approval_policy"] == "never"
    assert action.to_dict()["audit_stage"] == "browser_read"
    assert approval.to_dict()["status"] == "pending"
    assert audit.to_dict()["stage"] == "ingress"
    assert workflow.to_dict()["workflow_run_id"] == "wf_1"
