from __future__ import annotations

import pytest

from cli.agent_cli.gateway_core.models import ActionRequest, ApprovalTicket, AuditRecord
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from plugins.github_phase1.commands import (
    github_approval_approve_command,
    github_approval_reject_command,
    github_issue_comment_command,
    github_issue_create_command,
    github_workflow_dispatch_command,
)
from workers.actions.protocol import ActionResult

class _FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke_plugin_tool(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        return ToolEvent(
            name=name,
            ok=True,
            summary=f"{name} ok",
            payload={"ok": True, "called_with": kwargs},
        )

class _FakeRuntime:
    def __init__(self) -> None:
        self.tools = _FakeTools()
        self.decisions: list[dict[str, object]] = []

    def decide_gateway_approval(self, approval_id: str, *, approved: bool, decided_by: str, decision_note: str = ""):
        self.decisions.append(
            {
                "approval_id": approval_id,
                "approved": approved,
                "decided_by": decided_by,
                "decision_note": decision_note,
            }
        )
        return {
            "approval_ticket": ApprovalTicket(
                approval_id=approval_id,
                action_id="action_1",
                trace_id="trace_1",
                status="approved" if approved else "rejected",
                requested_at="2026-03-27T00:00:00+00:00",
                requested_by="cli",
                reason="reason",
                summary="summary",
            ),
            "action_request": ActionRequest(
                action_id="action_1",
                action_type="github.issue.comment",
                connector_key="github_webhook",
                plugin_name="github_phase1",
                trace_id="trace_1",
                requested_at="2026-03-27T00:00:00+00:00",
                requested_by="cli",
                approval_required=True,
                payload={"action": "http_request"},
            ),
            "action_result": ActionResult(
                ok=approved,
                action="http_request",
                summary="executed" if approved else "not executed",
                output={"status": "ok" if approved else "skipped"},
                correlation_id="trace_1",
            )
            if approved
            else None,
            "audit_records": [
                AuditRecord(
                    audit_id="audit_1",
                    trace_id="trace_1",
                    stage="approval",
                    created_at="2026-03-27T00:00:00+00:00",
                    status="approved" if approved else "rejected",
                    summary="decision made",
                    approval_id=approval_id,
                )
            ],
        }

@pytest.mark.parametrize(
    ("handler", "arg_text", "expected"),
    [
        (github_issue_create_command, "", "Usage: /github_issue_create repo <owner/repo> title <text> [body <text>]"),
        (
            github_issue_comment_command,
            "repo acme/platform issue-number 7",
            "Usage: /github_issue_comment repo <owner/repo> issue-number <n> body <text>",
        ),
        (
            github_workflow_dispatch_command,
            "repo acme/platform workflow-id deploy.yml",
            "Usage: /github_workflow_dispatch repo <owner/repo> workflow-id <id> ref <ref> [inputs-json <json>]",
        ),
    ],
)
def test_github_commands_return_usage_when_required_args_missing(handler, arg_text: str, expected: str) -> None:
    text, events = handler(arg_text, runtime=_FakeRuntime())

    assert text == expected
    assert events == []

def test_github_workflow_dispatch_command_rejects_invalid_inputs_json() -> None:
    text, events = github_workflow_dispatch_command(
        "repo acme/platform workflow-id deploy.yml ref main inputs-json '{bad json}'",
        runtime=_FakeRuntime(),
    )

    assert text == "Usage: /github_workflow_dispatch repo <owner/repo> workflow-id <id> ref <ref> [inputs-json <json>]"
    assert events == []

def test_github_workflow_dispatch_command_invokes_plugin_tool_with_decoded_inputs() -> None:
    runtime = _FakeRuntime()

    result = github_workflow_dispatch_command(
        'repo acme/platform workflow-id deploy.yml ref main inputs-json \'{"trace_id":"t1"}\' token-env PM_GITHUB_TOKEN',
        runtime=runtime,
    )
    assert isinstance(result, CommandExecutionResult)

    assert "Request GitHub workflow dispatch." in result.assistant_text
    assert [item.name for item in result.tool_events] == ["github_workflow_dispatch"]
    assert runtime.tools.calls[0][0] == "github_workflow_dispatch"
    assert runtime.tools.calls[0][1]["owner"] == "acme"
    assert runtime.tools.calls[0][1]["repo"] == "platform"
    assert runtime.tools.calls[0][1]["inputs"] == {"trace_id": "t1"}
    assert runtime.tools.calls[0][1]["token_env"] == "PM_GITHUB_TOKEN"
    assert result.item_events[0]["item"]["type"] == "mcp_tool_call"
    assert result.item_events[-1]["item"]["tool"] == "github_workflow_dispatch"

def test_github_approval_approve_command_calls_runtime_and_returns_tool_event() -> None:
    runtime = _FakeRuntime()

    result = github_approval_approve_command(
        "approval-id approval_1 decided-by tester decision-note approved",
        runtime=runtime,
    )
    assert isinstance(result, CommandExecutionResult)

    assert result.assistant_text == "Approve and execute GitHub action."
    assert [item.name for item in result.tool_events] == ["github_approval_approve"]
    assert runtime.decisions == [
        {
            "approval_id": "approval_1",
            "approved": True,
            "decided_by": "tester",
            "decision_note": "approved",
        }
    ]
    assert result.tool_events[0].payload["approval_ticket"]["status"] == "approved"
    assert result.tool_events[0].payload["action_result"]["summary"] == "executed"
    assert result.item_events[-1]["item"]["tool"] == "github_approval_approve"

def test_github_approval_reject_command_calls_runtime_and_returns_tool_event() -> None:
    runtime = _FakeRuntime()

    result = github_approval_reject_command(
        "approval-id approval_2 decided-by tester decision-note rejected",
        runtime=runtime,
    )
    assert isinstance(result, CommandExecutionResult)

    assert result.assistant_text == "Reject GitHub action."
    assert [item.name for item in result.tool_events] == ["github_approval_reject"]
    assert runtime.decisions == [
        {
            "approval_id": "approval_2",
            "approved": False,
            "decided_by": "tester",
            "decision_note": "rejected",
        }
    ]
    assert result.tool_events[0].payload["approval_ticket"]["status"] == "rejected"
    assert result.tool_events[0].payload["action_result"] is None
    assert result.item_events[-1]["item"]["tool"] == "github_approval_reject"
