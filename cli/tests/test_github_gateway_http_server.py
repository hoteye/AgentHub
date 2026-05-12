from __future__ import annotations

import json
from unittest.mock import patch

from cli.agent_cli.gateway_api import process_github_webhook
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from shared.integrations import compute_hmac_sha256_hex

class _GitHubServerFakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("LLM planner should not be used in github gateway server tests")

def test_process_github_webhook_routes_issue_opened_event() -> None:
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "issue": {"number": 1, "title": "Need review"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    secret = "webhook-secret"
    headers = {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": "sha256=" + compute_hmac_sha256_hex(secret, raw_body),
    }
    runtime = AgentCliRuntime(tools=ToolRegistry(), agent=_GitHubServerFakeAgent())

    status, response = process_github_webhook(runtime, headers=headers, raw_body=raw_body, webhook_secret=secret)

    assert status == 202
    assert response["ok"] is True
    assert response["event_type"] == "github.issues.opened"
    assert response["plugin_name"] == "github_phase1"
    assert response["workflow_name"] == "handle_github_issue_opened"
    assert response["correlation_id"] == "delivery-1"

def test_process_github_webhook_enters_through_dispatcher_method() -> None:
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "issue": {"number": 1, "title": "Need review"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    runtime = AgentCliRuntime(tools=ToolRegistry(), agent=_GitHubServerFakeAgent())

    with patch("cli.agent_cli.gateway_api.github_http_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = type(
            "Outcome",
            (),
            {
                "ok": True,
                "result": {
                    "event": {
                        "event_id": "evt_1",
                        "event_type": "github.issues.opened",
                        "trace_id": "trace_1",
                        "correlation_id": "delivery-1",
                    },
                    "decision": {
                        "targetKind": "workflow",
                        "pluginName": "github_phase1",
                        "workflowName": "handle_github_issue_opened",
                    },
                    "workflowRun": {"workflow_run_id": "wf_1"},
                },
            },
        )()
        status, response = process_github_webhook(
            runtime,
            headers={"X-GitHub-Event": "issues", "X-GitHub-Delivery": "delivery-1"},
            raw_body=raw_body,
            webhook_secret=None,
        )

    assert status == 202
    assert response["workflow_run_id"] == "wf_1"
    call = dispatch_mock.call_args.kwargs
    assert call["method"] == "github.webhook.ingest"
    assert call["params"]["connectorKey"] == "github_webhook"
    assert call["client_info"]["gatewayAuth"]["role"] == "webhook"

def test_process_github_webhook_rejects_invalid_signature() -> None:
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "issue": {"number": 1},
    }
    runtime = AgentCliRuntime(tools=ToolRegistry(), agent=_GitHubServerFakeAgent())

    status, response = process_github_webhook(
        runtime,
        headers={
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
        raw_body=json.dumps(payload).encode("utf-8"),
        webhook_secret="webhook-secret",
    )

    assert status == 401
    assert response == {"ok": False, "error": "invalid_signature"}
    assert runtime.gateway_state_store.list_events(limit=5) == []
    assert runtime.gateway_state_store.list_audit_records(limit=5) == []

def test_process_github_webhook_routes_issue_comment_created_event() -> None:
    payload = {
        "action": "created",
        "repository": {"full_name": "acme/platform"},
        "issue": {"number": 7, "title": "Need review"},
        "comment": {"body": "please check", "user": {"login": "alice"}},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    secret = "webhook-secret"
    headers = {
        "X-GitHub-Event": "issue_comment",
        "X-GitHub-Delivery": "delivery-2",
        "X-Hub-Signature-256": "sha256=" + compute_hmac_sha256_hex(secret, raw_body),
    }
    runtime = AgentCliRuntime(tools=ToolRegistry(), agent=_GitHubServerFakeAgent())

    status, response = process_github_webhook(runtime, headers=headers, raw_body=raw_body, webhook_secret=secret)

    assert status == 202
    assert response["ok"] is True
    assert response["event_type"] == "github.issue_comment.created"
    assert response["plugin_name"] == "github_phase1"
    assert response["workflow_name"] == "handle_github_issue_comment_created"
    assert response["correlation_id"] == "delivery-2"
