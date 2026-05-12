from __future__ import annotations

import os
from unittest.mock import patch

from cli.agent_cli.gateway_server.methods.github import GITHUB_FAMILY, github_handlers

def test_github_family_freezes_first_connector_method_names() -> None:
    assert GITHUB_FAMILY.methods == (
        "github.webhook.ingest",
        "github.actions.dispatch",
        "github.issues.create",
        "github.comments.create",
    )
    assert set(github_handlers) == set(GITHUB_FAMILY.methods)

class _Item:
    def __init__(self, payload):
        self.payload = dict(payload)

    def to_dict(self):
        return dict(self.payload)

    def __getattr__(self, name: str):
        try:
            return self.payload[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

class _Runtime:
    @staticmethod
    def request_gateway_action(**kwargs):
        return {
            "action_request": _Item({"action_id": "action_1", "action_type": kwargs.get("action_type")}),
            "approval_ticket": _Item({"approval_id": "approval_1", "status": "pending"}),
            "audit_records": [_Item({"audit_id": "audit_1"})],
        }

    @staticmethod
    def dispatch_gateway_event(event):
        return {
            "event": event,
            "decision": type(
                "Decision",
                (),
                {
                    "target_kind": "workflow",
                    "plugin_name": "github_phase1",
                    "workflow_name": "handle_github_issue_opened",
                    "reason": "matched trigger",
                },
            )(),
            "workflow_run": _Item({"workflow_run_id": "wf_1", "trace_id": getattr(event, "trace_id", "trace_1")}),
            "audit_records": [_Item({"audit_id": "audit_1"})],
        }

def test_github_handler_creates_real_approval_gated_issue_action() -> None:
    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        result = github_handlers["github.issues.create"](
            params={"repo": "hoteye/simulate-app", "title": "Need review"},
            runtime=_Runtime(),
        )

    assert result["method"] == "github.issues.create"
    assert result["status"] == "approval_required"
    assert result["approvalTicket"]["approval_id"] == "approval_1"
    assert result["actionRequest"]["action_type"] == "github.issue.create"

def test_github_handler_ingests_webhook_via_github_family() -> None:
    result = github_handlers["github.webhook.ingest"](
        params={
            "headers": {"X-GitHub-Event": "issues", "X-GitHub-Delivery": "delivery-1"},
            "rawBody": '{"action":"opened","repository":{"full_name":"acme/platform"},"issue":{"number":1}}',
        },
        runtime=_Runtime(),
    )

    assert result["method"] == "github.webhook.ingest"
    assert result["status"] == "accepted"
    assert result["decision"]["workflowName"] == "handle_github_issue_opened"
