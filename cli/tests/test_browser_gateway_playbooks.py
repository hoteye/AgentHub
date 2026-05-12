from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.gateway_api.gui_bridge_api import dispatch_gui_bridge_action
from cli.agent_cli.runtime import AgentCliRuntime
from workers.actions import ActionResult
from shared.web_automation.config import BrowserAutomationConfig

class _BrowserPlaybookAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_model": "gpt-5.4",
            "model_key": "gpt_5_4",
            "provider_label": "openai | gpt-5.4",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("planner should not run in browser gateway playbook tests")

class _FakeBrowserExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, action_request) -> ActionResult:
        browser_request = dict((action_request.payload or {}).get("browser_request") or {})
        self.calls.append(
            {
                "action_type": action_request.action_type,
                "workflow_run_id": action_request.workflow_run_id,
                "request": dict(browser_request),
            }
        )
        action_name = str(browser_request.get("action") or "snapshot")
        ref = str(browser_request.get("ref") or "")
        target_id = str(browser_request.get("target_id") or "tab-1")
        output = {
            "ok": True,
            "action": action_name,
            "target_id": target_id,
            "url": str(browser_request.get("url") or "https://example.com/app"),
            "ref": ref or None,
            "path": f"/tmp/{action_name or 'browser'}.txt",
        }
        summary = f"executed {action_name}"
        if ref:
            summary += f" on {ref}"
        return ActionResult(
            ok=True,
            action=str(action_request.action_type or ""),
            summary=summary,
            output=output,
        )

def _runtime_with_browser_executor(executor: _FakeBrowserExecutor) -> AgentCliRuntime:
    return AgentCliRuntime(
        agent=_BrowserPlaybookAgent(),
        browser_action_executor=executor,
    )

def test_browser_workflow_verify_executes_read_only_playbook_and_records_trace() -> None:
    executor = _FakeBrowserExecutor()
    runtime = _runtime_with_browser_executor(executor)

    response = dispatch_gui_bridge_action(
        runtime,
        action="browser.workflow.verify",
        request_id="req_browser_verify",
        payload={
            "profile": "openclaw",
            "target_id": "tab-verify",
            "reasoning_summary": "verify current browser page state",
            "evidence_refs": ["snapshot://seed"],
        },
    )

    assert response["ok"] is True
    assert response["data"]["mode"] == "executed"
    assert response["data"]["workflow_run"]["status"] == "ok"
    assert response["data"]["action_request"]["approval_required"] is False
    assert response["data"]["action_result"]["ok"] is True
    assert len(executor.calls) == 1
    assert executor.calls[0]["action_type"] == "browser.snapshot"

    snapshot = runtime.gateway_state_snapshot(limit=20)
    workflow_diag = snapshot["diagnostics"]["workflow_diagnostics"][0]

    assert workflow_diag["workflow_name"] == "browser_read_verify"
    assert workflow_diag["browser_workflow"]["playbook_kind"] == "read_verify"
    assert workflow_diag["browser_workflow"]["status"] == "completed"
    assert workflow_diag["recommendation"]["items"][0]["action_type"] == "browser.snapshot"
    assert workflow_diag["execution"]["status"] == "ok"
    assert workflow_diag["execution"]["browser_execution"]["action_type"] == "browser.snapshot"

def test_browser_workflow_mutate_waits_for_approval_then_executes_once() -> None:
    executor = _FakeBrowserExecutor()
    runtime = _runtime_with_browser_executor(executor)

    proposed = dispatch_gui_bridge_action(
        runtime,
        action="browser.workflow.mutate",
        request_id="req_browser_mutate",
        payload={
            "profile": "openclaw",
            "target_id": "tab-mutate",
            "kind": "click",
            "ref": "e4",
            "reasoning_summary": "submit the current form",
            "approval_summary": "Approve browser click submit",
            "evidence_refs": ["snapshot://before-submit"],
        },
    )

    assert proposed["ok"] is True
    assert proposed["data"]["mode"] == "approval_required"
    assert proposed["data"]["workflow_run"]["status"] == "approval_requested"
    assert proposed["data"]["approval_ticket"]["status"] == "pending"
    assert len(executor.calls) == 0

    approval_id = proposed["data"]["approval_ticket"]["approval_id"]
    resolved = dispatch_gui_bridge_action(
        runtime,
        action="approval.resolve",
        request_id="req_browser_mutate_approve",
        payload={"approval_id": approval_id, "decision": "approved", "decided_by": "tester"},
    )

    assert resolved["ok"] is True
    assert resolved["data"]["status"] == "approved"
    assert resolved["data"]["action_result"]["ok"] is True
    assert len(executor.calls) == 1
    assert executor.calls[0]["action_type"] == "browser.act.click"

    trace_id = proposed["data"]["trace_id"]
    audit = dispatch_gui_bridge_action(
        runtime,
        action="audit.list",
        request_id="req_browser_mutate_audit",
        payload={"trace_id": trace_id},
    )
    action_execute = [item for item in audit["data"]["records"] if item["stage"] == "action_execute"]

    assert len(action_execute) == 1
    assert action_execute[0]["details"]["browser_execution"]["action_type"] == "browser.act.click"

    snapshot = runtime.gateway_state_snapshot(limit=20)
    workflow_diag = snapshot["diagnostics"]["workflow_diagnostics"][0]
    approval_diag = snapshot["diagnostics"]["approval_diagnostics"][0]

    assert workflow_diag["workflow_name"] == "browser_mutate_after_approval"
    assert workflow_diag["browser_workflow"]["status"] == "completed"
    assert workflow_diag["approval"]["status"] == "approved"
    assert workflow_diag["execution"]["status"] == "ok"
    assert approval_diag["recommendation"]["action_class"] == "external_side_effecting"
    assert approval_diag["execution"]["browser_execution"]["action_type"] == "browser.act.click"

def test_browser_workflow_mutate_rejection_preserves_causality_without_execution() -> None:
    executor = _FakeBrowserExecutor()
    runtime = _runtime_with_browser_executor(executor)

    proposed = dispatch_gui_bridge_action(
        runtime,
        action="browser.workflow.mutate",
        request_id="req_browser_mutate_reject",
        payload={
            "profile": "openclaw",
            "target_id": "tab-reject",
            "kind": "click",
            "ref": "e9",
            "reasoning_summary": "propose dangerous click",
        },
    )
    approval_id = proposed["data"]["approval_ticket"]["approval_id"]

    resolved = dispatch_gui_bridge_action(
        runtime,
        action="approval.resolve",
        request_id="req_browser_mutate_reject_decision",
        payload={"approval_id": approval_id, "decision": "rejected", "decided_by": "tester"},
    )

    assert resolved["ok"] is True
    assert resolved["data"]["status"] == "rejected"
    assert len(executor.calls) == 0

    trace_id = proposed["data"]["trace_id"]
    audit = dispatch_gui_bridge_action(
        runtime,
        action="audit.list",
        request_id="req_browser_mutate_reject_audit",
        payload={"trace_id": trace_id},
    )

    assert not [item for item in audit["data"]["records"] if item["stage"] == "action_execute"]

    snapshot = runtime.gateway_state_snapshot(limit=20)
    workflow_diag = snapshot["diagnostics"]["workflow_diagnostics"][0]
    approval_diag = snapshot["diagnostics"]["approval_diagnostics"][0]

    assert workflow_diag["browser_workflow"]["status"] == "rejected"
    assert workflow_diag["approval"]["status"] == "rejected"
    assert workflow_diag["execution"]["status"] == "not_executed"
    assert approval_diag["approval"]["status"] == "rejected"

def test_default_browser_executor_keeps_existing_session_profile_local_even_when_proxy_requested() -> None:
    runtime = AgentCliRuntime(agent=_BrowserPlaybookAgent())
    action_request = SimpleNamespace(
        action_type="browser.snapshot",
        payload={"browser_request": {"transport": "proxy", "action": "snapshot", "profile": "user"}},
    )

    with (
        patch("shared.web_automation.config.load_config", return_value=BrowserAutomationConfig(mode="live")),
        patch("shared.web_automation.client.BrowserClient.perform", return_value={"ok": True, "action": "snapshot"}) as browser_perform,
        patch("shared.web_automation.proxy.BrowserProxyExecutor.run") as proxy_run,
    ):
        result = runtime._default_browser_action_executor(action_request)

    assert result.ok is True
    browser_perform.assert_called_once()
    proxy_run.assert_not_called()

def test_default_browser_executor_uses_proxy_for_non_existing_session_profile_when_requested() -> None:
    runtime = AgentCliRuntime(agent=_BrowserPlaybookAgent())
    action_request = SimpleNamespace(
        action_type="browser.snapshot",
        payload={"browser_request": {"transport": "proxy", "action": "snapshot", "profile": "openclaw"}},
    )

    with (
        patch("shared.web_automation.config.load_config", return_value=BrowserAutomationConfig(mode="live")),
        patch("shared.web_automation.client.BrowserClient.perform") as browser_perform,
        patch(
            "shared.web_automation.proxy.BrowserProxyExecutor.run",
            return_value={"status": 200, "result": {"ok": True, "action": "snapshot"}},
        ) as proxy_run,
    ):
        result = runtime._default_browser_action_executor(action_request)

    assert result.ok is True
    proxy_run.assert_called_once()
    browser_perform.assert_not_called()
