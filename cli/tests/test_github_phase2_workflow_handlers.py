from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.gateway_api import build_webhook_event
from cli.agent_cli.gateway_core import InMemoryGatewayStateStore
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from plugins.github_phase1 import workflow_handlers as github_workflow_handlers
from plugins.github_phase1.workflow_handlers import (
    build_workflow_handlers,
    handle_github_compliance_issue_opened,
    handle_github_issue_comment_created,
    handle_github_issue_opened,
)
from shared.integrations import github_source_id, normalize_github_event_type

class _GitHubPhase2FakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("LLM planner should not be used in github phase2 workflow handler tests")

def _sample_issue_event(*, trace_id: str = "trace_phase2") -> SimpleNamespace:
    return SimpleNamespace(
        event_id="evt_phase2_1",
        trace_id=trace_id,
        correlation_id="",
        payload={
            "repository": {
                "full_name": "acme/platform",
                "html_url": "https://github.com/acme/platform",
            },
            "issue": {
                "number": 42,
                "title": "Need compliance review",
                "html_url": "https://github.com/acme/platform/issues/42",
            },
        },
    )

def test_build_workflow_handlers_matches_trigger_workflow_names() -> None:
    handlers = build_workflow_handlers()
    names = {item["workflow_name"] for item in handlers}

    assert names == {
        "handle_github_compliance_issue_opened",
        "handle_github_issue_opened",
        "handle_github_issue_comment_created",
    }
    assert all(callable(item["handler"]) for item in handlers)
    assert all(item["plugin_name"] == "github_phase1" for item in handlers)

def test_handle_github_issue_opened_emits_one_approval_gated_action_request_with_same_trace() -> None:
    event = _sample_issue_event(trace_id="trace_abc")
    decision = SimpleNamespace(workflow_name="handle_github_issue_opened")
    workflow_run = SimpleNamespace(workflow_run_id="wf_abc")
    runtime = object()
    fake_tool_event = ToolEvent(
        name="github_issue_comment",
        ok=True,
        summary="approval requested: approval_1",
        payload={
            "mode": "approval_required",
            "action_request": {
                "action_id": "action_1",
                "trace_id": "trace_abc",
                "event_id": "evt_phase2_1",
                "workflow_run_id": "wf_abc",
            },
        },
    )

    with patch.object(github_workflow_handlers.github_tools, "github_issue_comment", return_value=fake_tool_event) as mock_tool:
        result = handle_github_issue_opened(
            event=event,
            decision=decision,
            workflow_run=workflow_run,
            runtime=runtime,
        )

    assert result["status"] == "approval_requested"
    assert result["trace_id"] == "trace_abc"
    assert result["workflow_run_id"] == "wf_abc"
    assert len(result["action_requests"]) == 1
    assert result["action_requests"][0]["action_id"] == "action_1"
    assert "approval-gated" in result["reasoning_summary"]
    assert "https://github.com/acme/platform/issues/42" in result["evidence_refs"]
    kwargs = mock_tool.call_args.kwargs
    assert kwargs["owner"] == "acme"
    assert kwargs["repo"] == "platform"
    assert kwargs["issue_number"] == 42
    assert kwargs["correlation_id"] == "trace_abc"
    assert kwargs["event_id"] == "evt_phase2_1"
    assert kwargs["workflow_run_id"] == "wf_abc"
    assert kwargs["metadata"]["workflow_name"] == "handle_github_issue_opened"
    assert kwargs["metadata"]["reasoning_summary"] == result["reasoning_summary"]
    assert kwargs["runtime"] is runtime

def test_handle_github_compliance_issue_opened_marks_compliance_route_in_followup_body() -> None:
    event = _sample_issue_event(trace_id="trace_compliance")
    decision = SimpleNamespace(workflow_name="handle_github_compliance_issue_opened")
    workflow_run = SimpleNamespace(workflow_run_id="wf_compliance")
    runtime = object()
    fake_tool_event = ToolEvent(
        name="github_issue_comment",
        ok=True,
        summary="approval requested: approval_2",
        payload={"mode": "approval_required", "action_request": {"action_id": "action_2"}},
    )

    with patch.object(github_workflow_handlers.github_tools, "github_issue_comment", return_value=fake_tool_event) as mock_tool:
        result = handle_github_compliance_issue_opened(
            event=event,
            decision=decision,
            workflow_run=workflow_run,
            runtime=runtime,
        )

    assert result["status"] == "approval_requested"
    assert "compliance workflow" in result["reasoning_summary"]
    assert "compliance route" in mock_tool.call_args.kwargs["body"]

def test_handle_github_issue_comment_created_returns_structured_noop() -> None:
    event = SimpleNamespace(
        event_id="evt_comment_1",
        trace_id="trace_comment",
        correlation_id="corr_comment",
        payload={
            "repository": {"full_name": "acme/platform", "html_url": "https://github.com/acme/platform"},
            "issue": {"number": 42, "html_url": "https://github.com/acme/platform/issues/42"},
            "comment": {"id": 7, "body": "hello"},
        },
    )
    decision = SimpleNamespace(workflow_name="handle_github_issue_comment_created")
    workflow_run = SimpleNamespace(workflow_run_id="wf_comment")

    result = handle_github_issue_comment_created(
        event=event,
        decision=decision,
        workflow_run=workflow_run,
        runtime=object(),
    )

    assert result["status"] == "noop"
    assert result["action_requests"] == []
    assert result["trace_id"] == "trace_comment"
    assert result["correlation_id"] == "corr_comment"
    assert "no follow-up action requested" in result["reasoning_summary"]

def test_runtime_dispatch_github_issue_event_creates_same_trace_approval_with_upstream_ids() -> None:
    payload = {
        "action": "opened",
        "repository": {
            "full_name": "acme/platform",
            "html_url": "https://github.com/acme/platform",
        },
        "issue": {
            "number": 42,
            "title": "Need compliance review",
            "html_url": "https://github.com/acme/platform/issues/42",
        },
    }
    headers = {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-phase2-1",
    }
    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubPhase2FakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
    )
    event = build_webhook_event(
        connector_key="github_webhook",
        event_type=normalize_github_event_type(headers=headers, payload=payload),
        payload=payload,
        headers=headers,
        source_id=github_source_id(payload),
    )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        result = runtime.dispatch_gateway_event(event)

    workflow_run = result["workflow_run"]
    workflow_result = result["workflow_result"]
    assert workflow_run is not None
    assert workflow_result is not None
    assert workflow_result["status"] == "approval_requested"
    assert len(workflow_result["action_requests"]) == 1

    action_request = runtime.gateway_state_store.list_action_requests(limit=5)[0]
    approval_ticket = runtime.gateway_state_store.list_approval_tickets(limit=5)[0]
    assert action_request.trace_id == event.trace_id
    assert action_request.event_id == event.event_id
    assert action_request.workflow_run_id == workflow_run.workflow_run_id
    assert action_request.metadata["workflow_name"] == result["decision"].workflow_name
    assert approval_ticket.metadata["source_event_id"] == event.event_id
    assert approval_ticket.metadata["source_workflow_run_id"] == workflow_run.workflow_run_id

def test_runtime_dispatch_issue_comment_created_continues_into_structured_noop_workflow() -> None:
    payload = {
        "action": "created",
        "repository": {
            "full_name": "acme/platform",
            "html_url": "https://github.com/acme/platform",
        },
        "issue": {
            "number": 42,
            "title": "Need compliance review",
            "html_url": "https://github.com/acme/platform/issues/42",
        },
        "comment": {
            "id": 7,
            "body": "please review",
            "html_url": "https://github.com/acme/platform/issues/42#issuecomment-7",
        },
    }
    headers = {
        "X-GitHub-Event": "issue_comment",
        "X-GitHub-Delivery": "delivery-phase2-comment-1",
    }
    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubPhase2FakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
    )
    event = build_webhook_event(
        connector_key="github_webhook",
        event_type=normalize_github_event_type(headers=headers, payload=payload),
        payload=payload,
        headers=headers,
        source_id=github_source_id(payload),
    )

    result = runtime.dispatch_gateway_event(event)

    workflow_run = result["workflow_run"]
    workflow_result = result["workflow_result"]
    assert result["decision"].workflow_name == "handle_github_issue_comment_created"
    assert workflow_run is not None
    assert workflow_result is not None
    assert workflow_result["status"] == "noop"
    assert workflow_result["action_requests"] == []
    assert "no follow-up action requested" in workflow_result["reasoning_summary"]
    assert runtime.gateway_state_store.list_action_requests(limit=5) == []
    assert runtime.gateway_state_store.list_approval_tickets(limit=5) == []

    workflow_audits = runtime.gateway_state_store.list_audit_records(
        trace_id=event.trace_id,
        stage="workflow",
        workflow_run_id=workflow_run.workflow_run_id,
        limit=5,
    )
    assert len(workflow_audits) == 1
    assert workflow_audits[0].status == "noop"
    assert workflow_audits[0].details["workflow_name"] == "handle_github_issue_comment_created"
