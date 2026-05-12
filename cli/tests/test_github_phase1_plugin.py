from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.gateway_api import build_webhook_event
from cli.agent_cli.gateway_core import InMemoryGatewayStateStore
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from plugins.github_phase1 import tools as github_tools
from shared.integrations import HttpClient, github_source_id, normalize_github_event_type
from workers.actions import ControlledActionWorker


class _GitHubFakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("LLM planner should not be used in github phase1 plugin tests")


def test_github_phase1_plugin_is_discovered_with_gateway_registrations() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = PluginManager(state_path=Path(tmpdir) / "plugin_state.json")

        plugins = manager.list_plugins()
        assert any(
            item["name"] == "github_phase1"
            and item["enabled"]
            and item["connector_count"] == 1
            and item["trigger_count"] == 3
            and item["policy_count"] == 1
            for item in plugins
        )
        assert any(item["name"] == "github_issue_create" for item in manager.command_specs())
        assert any(item["name"] == "github_issue_create" for item in manager.tool_specs())
        assert (
            manager.connector_registrations_for_plugin("github_phase1")[0].connector_key
            == "github_webhook"
        )
        assert (
            manager.policy_registrations_for_plugin("github_phase1")[0].policy_key
            == "github_mutation_approval"
        )


def test_github_phase1_issue_create_tool_executes_controlled_http_request() -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str) -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse(
            url=request.full_url,
            status_code=201,
            body=json.dumps({"html_url": "https://github.com/acme/platform/issues/1"}),
        )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_issue_create(
            owner="acme",
            repo="platform",
            title="Phase 1 validation",
            body="created by test",
            token_env="GITHUB_TOKEN",
            http_client=HttpClient(open_url=_open),
        )

    assert event.ok is True
    assert captured["url"] == "https://api.github.com/repos/acme/platform/issues"
    assert captured["method"] == "POST"
    assert json.loads(str(captured["body"]))["title"] == "Phase 1 validation"
    assert event.payload["output"]["json_data"]["html_url"].endswith("/issues/1")


def test_github_issue_opened_webhook_routes_to_github_phase1_workflow() -> None:
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "issue": {"number": 42, "title": "Need compliance review"},
    }
    headers = {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": "sha256=secret",
    }
    event_type = normalize_github_event_type(headers=headers, payload=payload)

    tools = ToolRegistry()
    runtime = AgentCliRuntime(tools=tools, agent=_GitHubFakeAgent())
    event = build_webhook_event(
        connector_key="github_webhook",
        event_type=event_type,
        payload=payload,
        headers=headers,
        source_id=github_source_id(payload),
    )

    result = runtime.dispatch_gateway_event(event)

    assert result["decision"].plugin_name == "github_phase1"
    assert result["decision"].workflow_name == "handle_github_compliance_issue_opened"
    assert result["event"].source_id == "github:acme/platform"
    assert result["event"].metadata["headers"]["X-Hub-Signature-256"] == "***"


def test_github_issue_create_requests_approval_and_executes_only_after_decision() -> None:
    captured: dict[str, object] = {"calls": 0}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str) -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["calls"] = int(captured["calls"]) + 1
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse(
            url=request.full_url,
            status_code=201,
            body=json.dumps({"html_url": "https://github.com/acme/platform/issues/9"}),
        )

    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
        action_worker=ControlledActionWorker(http_client=HttpClient(open_url=_open)),
    )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_issue_create(
            owner="acme",
            repo="platform",
            title="Phase 1 approval path",
            body="created after approval",
            token_env="GITHUB_TOKEN",
            runtime=runtime,
        )

    assert event.ok is True
    assert event.payload["mode"] == "approval_required"
    assert captured["calls"] == 0
    assert "Authorization" not in (
        ((event.payload["request"] or {}).get("parameters") or {}).get("headers") or {}
    )
    assert (((event.payload["request"] or {}).get("parameters") or {}).get("auth") or {}).get(
        "token_env"
    ) == "GITHUB_TOKEN"

    approval_id = event.payload["approval_ticket"]["approval_id"]
    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        decision = runtime.decide_gateway_approval(approval_id, approved=True, decided_by="test")

    assert decision["approval_ticket"].status == "approved"
    assert decision["action_result"] is not None
    assert decision["action_result"].ok is True
    assert captured["calls"] == 1
    assert captured["url"] == "https://api.github.com/repos/acme/platform/issues"
    assert any(item.stage == "action_execute" for item in decision["audit_records"])


def test_github_issue_comment_rejection_records_audit_without_executing_http() -> None:
    captured: dict[str, object] = {"calls": 0}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str) -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["calls"] = int(captured["calls"]) + 1
        return _FakeResponse(
            url=request.full_url,
            status_code=201,
            body=json.dumps(
                {"html_url": "https://github.com/acme/platform/issues/9#issuecomment-1"}
            ),
        )

    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
        action_worker=ControlledActionWorker(http_client=HttpClient(open_url=_open)),
    )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_issue_comment(
            owner="acme",
            repo="platform",
            issue_number=9,
            body="do not send",
            token_env="GITHUB_TOKEN",
            runtime=runtime,
        )

    approval_id = event.payload["approval_ticket"]["approval_id"]
    decision = runtime.decide_gateway_approval(approval_id, approved=False, decided_by="test")

    assert decision["approval_ticket"].status == "rejected"
    assert decision["action_result"] is None
    assert captured["calls"] == 0
    assert [item.stage for item in decision["audit_records"]] == ["approval"]
    assert [item.status for item in decision["audit_records"]] == ["rejected"]


def test_inbound_github_issue_rejection_preserves_same_trace_causality_without_writeback() -> None:
    captured: dict[str, object] = {"calls": 0}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str) -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["calls"] = int(captured["calls"]) + 1
        return _FakeResponse(
            url=request.full_url,
            status_code=201,
            body=json.dumps(
                {"html_url": "https://github.com/acme/platform/issues/42#issuecomment-1"}
            ),
        )

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
        "X-GitHub-Delivery": "delivery-phase2-reject-1",
    }
    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
        action_worker=ControlledActionWorker(http_client=HttpClient(open_url=_open)),
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
    assert workflow_run is not None
    approval_ticket = runtime.gateway_state_store.list_approval_tickets(limit=5)[0]
    assert approval_ticket.trace_id == event.trace_id
    assert approval_ticket.metadata["source_event_id"] == event.event_id
    assert approval_ticket.metadata["source_workflow_run_id"] == workflow_run.workflow_run_id

    decision = runtime.decide_gateway_approval(
        approval_ticket.approval_id,
        approved=False,
        decided_by="test",
        decision_note="reject same-trace follow-up",
    )

    assert captured["calls"] == 0
    assert decision["approval_ticket"].status == "rejected"
    assert decision["action_result"] is None
    assert decision["action_request"].trace_id == event.trace_id
    assert decision["action_request"].event_id == event.event_id
    assert decision["action_request"].workflow_run_id == workflow_run.workflow_run_id
    assert [item.stage for item in decision["audit_records"]] == ["approval"]
    assert [item.status for item in decision["audit_records"]] == ["rejected"]

    approval_records = runtime.gateway_state_store.list_audit_records(
        trace_id=event.trace_id,
        stage="approval",
        approval_id=approval_ticket.approval_id,
        limit=10,
    )
    assert len(approval_records) == 2
    assert sorted(item.status for item in approval_records) == ["pending", "rejected"]
    assert (
        runtime.gateway_state_store.list_audit_records(
            trace_id=event.trace_id,
            stage="action_execute",
            approval_id=approval_ticket.approval_id,
            limit=10,
        )
        == []
    )

    timeline = runtime.gateway_state_store.trace_timeline(event.trace_id, limit=20)
    assert len(timeline) == 6
    assert {item.stage for item in timeline} == {
        "ingress",
        "route",
        "workflow",
        "action_request",
        "approval",
    }


def test_github_issue_create_failure_records_failed_action_execute_audit() -> None:
    captured: dict[str, object] = {"calls": 0}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str) -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["calls"] = int(captured["calls"]) + 1
        return _FakeResponse(
            url=request.full_url,
            status_code=410,
            body=json.dumps({"message": "Issues are disabled for this repo"}),
        )

    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
        action_worker=ControlledActionWorker(http_client=HttpClient(open_url=_open)),
    )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_issue_create(
            owner="acme",
            repo="platform",
            title="Phase 1 failure path",
            body="expected to fail",
            token_env="GITHUB_TOKEN",
            runtime=runtime,
        )

    approval_id = event.payload["approval_ticket"]["approval_id"]
    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        decision = runtime.decide_gateway_approval(approval_id, approved=True, decided_by="test")

    assert captured["calls"] == 1
    assert decision["approval_ticket"].status == "approved"
    assert decision["action_result"] is None
    assert [item.stage for item in decision["audit_records"]] == ["approval", "action_execute"]
    assert decision["audit_records"][1].status == "failed"
    assert "unexpected status code: 410" in decision["audit_records"][1].summary
    assert "status=410" in decision["audit_records"][1].details["error"]


def test_github_workflow_dispatch_is_denied_when_not_allowlisted() -> None:
    event = github_tools.github_workflow_dispatch(
        owner="acme",
        repo="platform",
        workflow_id="not-allowed.yml",
        ref="main",
        inputs={},
        token_env="GITHUB_TOKEN",
    )

    assert event.ok is False
    assert event.payload["reason"] == "workflow_not_allowlisted"


def test_github_workflow_dispatch_denial_is_persisted_in_runtime_state() -> None:
    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
    )

    event = github_tools.github_workflow_dispatch(
        owner="acme",
        repo="platform",
        workflow_id="not-allowed.yml",
        ref="main",
        inputs={"note": "deny me"},
        token_env="GITHUB_TOKEN",
        runtime=runtime,
    )

    assert event.ok is False
    assert event.payload["reason"] == "workflow_not_allowlisted"
    assert event.payload["action_request"]["action_type"] == "github.workflow.dispatch"
    assert event.payload["action_request"]["metadata"]["decision"] == "denied"
    audit_records = runtime.gateway_state_store.list_audit_records(limit=5)
    assert len(audit_records) == 1
    assert audit_records[0].status == "denied"
    assert audit_records[0].details["reason"] == "workflow_not_allowlisted"


def test_github_workflow_dispatch_injects_trace_inputs_for_allowlisted_workflow() -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {"Content-Type": "text/plain"}

        def read(self) -> bytes:
            return b""

        def getcode(self) -> int:
            return 204

        def geturl(self) -> str:
            return "https://api.github.com/repos/hoteye/simulate-app/actions/workflows/agenthub-validation.yml/dispatches"

    def _open(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse()

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_workflow_dispatch(
            owner="hoteye",
            repo="simulate-app",
            workflow_id="agenthub-validation.yml",
            ref="master",
            inputs={},
            token_env="GITHUB_TOKEN",
            http_client=HttpClient(open_url=_open),
        )

    assert event.ok is True
    assert captured["method"] == "POST"
    inputs = json.loads(str(captured["body"]))["inputs"]
    assert inputs.get("trace_id")
    assert inputs.get("correlation_id") == inputs.get("trace_id")


def test_github_workflow_dispatch_approval_success_records_workflow_run_artifacts() -> None:
    captured: dict[str, object] = {"calls": 0}

    class _FakeResponse:
        def __init__(self, *, url: str, status_code: int, body: str = "") -> None:
            self._url = url
            self._status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = (
                {"Content-Type": "application/json; charset=utf-8"}
                if body
                else {"Content-Type": "text/plain"}
            )

        def read(self) -> bytes:
            return self._body

        def getcode(self) -> int:
            return self._status_code

        def geturl(self) -> str:
            return self._url

    def _open(request, *, timeout):
        captured["calls"] = int(captured["calls"]) + 1
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse(url=request.full_url, status_code=204)

    runtime = AgentCliRuntime(
        tools=ToolRegistry(),
        agent=_GitHubFakeAgent(),
        gateway_state_store=InMemoryGatewayStateStore(),
        action_worker=ControlledActionWorker(http_client=HttpClient(open_url=_open)),
    )

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        event = github_tools.github_workflow_dispatch(
            owner="hoteye",
            repo="simulate-app",
            workflow_id="agenthub-validation.yml",
            ref="master",
            inputs={"note": "dispatch me"},
            token_env="GITHUB_TOKEN",
            runtime=runtime,
        )

    approval_id = event.payload["approval_ticket"]["approval_id"]
    trace_id = event.payload["approval_ticket"]["trace_id"]
    fake_run = {
        "run_id": 123,
        "run_number": 9,
        "html_url": "https://github.com/hoteye/simulate-app/actions/runs/123",
        "display_title": f"AgentHub validation {trace_id}",
        "status": "queued",
        "conclusion": None,
    }
    with patch("cli.agent_cli.runtime.find_github_workflow_run", return_value=fake_run) as find_run:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
            decision = runtime.decide_gateway_approval(
                approval_id, approved=True, decided_by="test"
            )

    assert decision["approval_ticket"].status == "approved"
    assert decision["action_result"] is not None
    assert decision["action_result"].ok is True
    assert captured["calls"] == 1
    assert captured["method"] == "POST"
    assert (
        captured["url"]
        == "https://api.github.com/repos/hoteye/simulate-app/actions/workflows/agenthub-validation.yml/dispatches"
    )
    assert json.loads(str(captured["body"]))["ref"] == "master"
    find_run.assert_called_once()
    action_execute = decision["audit_records"][1]
    assert action_execute.stage == "action_execute"
    assert action_execute.status == "ok"
    assert action_execute.details["github_workflow_run"]["run_id"] == 123
    assert action_execute.details["artifact_refs"] == [
        "https://github.com/hoteye/simulate-app/actions/runs/123"
    ]
    assert decision["approval_ticket"].evidence_refs == [
        "https://github.com/hoteye/simulate-app/actions/runs/123"
    ]
