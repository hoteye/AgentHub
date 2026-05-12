from __future__ import annotations

from cli.agent_cli.gateway_core.actions import create_action_request
from cli.agent_cli.gateway_core.approvals import create_approval_ticket
from cli.agent_cli.gateway_core.audit import create_audit_record
from cli.agent_cli.gateway_core.state_store import InMemoryGatewayStateStore

def test_create_approval_ticket_preserves_upstream_causality_metadata() -> None:
    action = create_action_request(
        action_type="github.issue.comment",
        connector_key="github_webhook",
        plugin_name="github_phase1",
        trace_id="trace_123",
        requested_by="workflow.github",
        workflow_run_id="wf_123",
        event_id="evt_123",
        metadata={
            "workflow_name": "handle_github_issue_opened",
            "reasoning_summary": "issue qualifies for follow-up comment",
            "evidence_refs": ["https://github.com/acme/repo/issues/1"],
        },
    )

    approval = create_approval_ticket(
        action,
        requested_by="workflow.github",
        reason="Phase 2 causality validation",
        summary="Approve follow-up comment",
    )

    assert approval.trace_id == "trace_123"
    assert approval.action_id == action.action_id
    assert approval.metadata["source_action_type"] == "github.issue.comment"
    assert approval.metadata["source_connector_key"] == "github_webhook"
    assert approval.metadata["source_plugin_name"] == "github_phase1"
    assert approval.metadata["source_event_id"] == "evt_123"
    assert approval.metadata["source_workflow_run_id"] == "wf_123"
    assert approval.metadata["workflow_name"] == "handle_github_issue_opened"
    assert approval.metadata["reasoning_summary"] == "issue qualifies for follow-up comment"
    assert approval.metadata["evidence_refs"] == ["https://github.com/acme/repo/issues/1"]
    assert approval.metadata["causality"] == {
        "action_id": action.action_id,
        "event_id": "evt_123",
        "workflow_run_id": "wf_123",
    }


def test_create_approval_ticket_persists_browser_action_policy_snapshot_copy() -> None:
    action = create_action_request(
        action_type="browser.act",
        connector_key="browser_proxy",
        plugin_name="easyclaw",
        trace_id="trace_browser_snapshot",
        requested_by="workflow.browser",
        payload={"kind": "click", "ref": "e9"},
    )

    approval = create_approval_ticket(
        action,
        requested_by="workflow.browser",
        reason="Phase 2 browser policy snapshot validation",
        summary="Approve browser click",
    )
    action.metadata["action_policy"]["decision"] = "blocked"

    assert approval.metadata["action_policy"]["action_kind"] == "browser"
    assert approval.metadata["action_policy"]["decision"] == "requires_approval"
    assert approval.metadata["action_policy"]["requirement"] == "needs_approval"

def test_create_audit_record_embeds_stage_group_and_causality_metadata() -> None:
    record = create_audit_record(
        trace_id="trace_abc",
        stage="workflow_reasoning",
        status="ok",
        summary="workflow produced recommendation",
        event_id="evt_1",
        workflow_run_id="wf_1",
        action_id="action_1",
        approval_id="approval_1",
        details={"reasoning_summary": "recommend comment"},
    )

    assert record.metadata["stage_group"] == "workflow_reasoning"
    assert record.metadata["causality"] == {
        "trace_id": "trace_abc",
        "event_id": "evt_1",
        "workflow_run_id": "wf_1",
        "action_id": "action_1",
        "approval_id": "approval_1",
    }
    assert record.details["reasoning_summary"] == "recommend comment"

def test_state_store_filters_audit_records_and_trace_timeline() -> None:
    store = InMemoryGatewayStateStore()
    trace_id = "trace_789"

    ingress = create_audit_record(
        trace_id=trace_id,
        stage="ingress",
        status="ok",
        summary="received github.issues.opened",
        event_id="evt_789",
    )
    approval = create_audit_record(
        trace_id=trace_id,
        stage="approval",
        status="approved",
        summary="approved github.issue.comment",
        event_id="evt_789",
        workflow_run_id="wf_789",
        action_id="action_789",
        approval_id="approval_789",
    )
    execute = create_audit_record(
        trace_id=trace_id,
        stage="action_execute",
        status="ok",
        summary="http request completed",
        event_id="evt_789",
        workflow_run_id="wf_789",
        action_id="action_789",
        approval_id="approval_789",
    )

    store.append_audit_record(ingress)
    store.append_audit_record(approval)
    store.append_audit_record(execute)

    filtered = store.list_audit_records(
        trace_id=trace_id,
        stage="approval",
        status="approved",
        event_id="evt_789",
        workflow_run_id="wf_789",
        action_id="action_789",
        approval_id="approval_789",
        limit=10,
    )
    assert [item.stage for item in filtered] == ["approval"]
    assert filtered[0].summary == "approved github.issue.comment"

    timeline = store.trace_timeline(trace_id, limit=10)
    assert [item.stage for item in timeline] == ["ingress", "approval", "action_execute"]

def test_state_store_filters_approval_tickets_by_trace_and_action() -> None:
    store = InMemoryGatewayStateStore()
    action_one = create_action_request(
        action_type="github.issue.comment",
        connector_key="github_webhook",
        plugin_name="github_phase1",
        trace_id="trace_one",
        requested_by="workflow",
    )
    action_two = create_action_request(
        action_type="github.issue.comment",
        connector_key="github_webhook",
        plugin_name="github_phase1",
        trace_id="trace_two",
        requested_by="workflow",
    )
    approval_one = create_approval_ticket(action_one, summary="one")
    approval_two = create_approval_ticket(action_two, summary="two")
    store.save_approval_ticket(approval_one)
    store.save_approval_ticket(approval_two)

    trace_filtered = store.list_approval_tickets(trace_id="trace_one", limit=10)
    assert [item.approval_id for item in trace_filtered] == [approval_one.approval_id]

    action_filtered = store.list_approval_tickets(action_id=action_two.action_id, limit=10)
    assert [item.approval_id for item in action_filtered] == [approval_two.approval_id]
