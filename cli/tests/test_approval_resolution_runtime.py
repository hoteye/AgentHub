# ruff: noqa: E402

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.gateway_core import WorkflowRun
from cli.agent_cli import approval_contract_runtime
from cli.agent_cli import runtime_exec_policy_rules
from cli.agent_cli.runtime_services import approval_projection_runtime
from cli.agent_cli.runtime_services import approval_resolution_gateway_runtime
from cli.agent_cli.runtime_services import approval_resolution_runtime
from cli.agent_cli.runtime_services import approval_ticket_runtime
from workers.actions import ActionResult

class _Agent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "test",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("planner should not run in approval resolution tests")

class _ActionWorker:
    @staticmethod
    def execute(request):
        return ActionResult(
            ok=True,
            action=str(request.get("action") or ""),
            summary="fake action executed",
            output={"artifact_refs": ["demo://artifact/1"]},
        )

class _Tools:
    PROJECT_ROOT = ROOT

    def __init__(self) -> None:
        self.shell_start_calls: list[str] = []

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        self.shell_start_calls.append(command)
        return {
            "session_id": "session_1",
            "call_id": "call_1",
            "process_id": "process_1",
            "command": command,
            "lifecycle": {
                "phase": "started",
                "kind": "begin",
                "call_id": "call_1",
                "session_id": "session_1",
                "process_id": "process_1",
                "status": "started",
            },
        }

    def shell(self, command: str, *, timeout_sec=60, on_activity=None, cancel_event=None) -> ToolEvent:
        raise AssertionError("shell exec_once path should not run in this test")


class _McpRuntimeStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call_projected_tool(self, *, projected_name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
        payload = {
            "ok": True,
            "projected_name": str(projected_name or ""),
            "server_name": "atlas",
            "remote_name": "search_docs",
            "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
            "approval": {
                "required": True,
                "family": "mcp_tool_call",
                "scope": "mcp.server:atlas",
            },
        }
        self.calls.append(
            {
                "projected_name": str(projected_name or ""),
                "arguments": dict(arguments or {}),
            }
        )
        return payload


def _request_mcp_gateway_action(runtime: AgentCliRuntime, *, label: str) -> dict[str, object]:
    return runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": label},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id=f"trace_mcp_guard_{label}",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="regression guard",
    )


def _assert_decision_event_shape(result: dict[str, object]) -> None:
    turn_events = result["turn_events"]
    item_events = result["item_events"]

    assert turn_events[0]["type"] == "turn.started"
    assert turn_events[-1]["type"] == "turn.completed"
    assert len(turn_events) == len(item_events) + 2

    assert [event["type"] for event in item_events] == ["item.started", "item.completed"]
    assert item_events[0]["item"]["status"] == "in_progress"
    assert item_events[-1]["item"]["status"] == "completed"
    assert all(event["item"]["tool"] == "approval_decision" for event in item_events)

    for turn_event, item_event in zip(turn_events[1:-1], item_events):
        assert turn_event == item_event


def test_decide_gateway_approval_preserves_artifact_refs_and_turn_events() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = runtime.request_gateway_action(
        action_type="demo.noop",
        connector_key="demo_webhook",
        plugin_name="demo_plugin",
        request_payload={"action": "noop", "parameters": {"ticket": "T-9"}},
        requested_by="workflow.demo",
        trace_id="trace_demo_1",
        approval_required=True,
        approval_summary="Approve demo noop",
        approval_reason="resolution test",
        metadata={"evidence_refs": ["demo://ticket/T-9"]},
    )

    result = approval_resolution_runtime.decide_gateway_approval(
        runtime,
        requested["approval_ticket"].approval_id,
        approved=True,
        decided_by="tester",
    )

    assert result["approval_ticket"].status == "approved"
    assert result["decision_outcome"] == "approved"
    assert result["action_result"].ok is True
    assert result["audit_records"][0].stage == "approval"
    assert result["audit_records"][0].details["decision_outcome"] == "approved"
    assert result["audit_records"][0].details["execution_skipped"] is False
    assert result["audit_records"][1].stage == "action_execute"
    execution_contract = result["audit_records"][1].details["execution_contract"]
    assert execution_contract["source"] == "gateway"
    assert execution_contract["tool_family"] == "gateway_action"
    assert execution_contract["action_type"] == "demo.noop"
    assert execution_contract["approval_required"] is True
    assert execution_contract["requires_confirmation"] is True
    assert execution_contract["mutates_ui"] is False
    assert result["turn_events"][0]["type"] == "turn.started"
    assert result["turn_events"][-1]["type"] == "turn.completed"
    assert any(item["item"]["tool"] == "gateway_action_execute" for item in result["item_events"])

def test_decide_shell_approval_session_start_returns_same_runtime_payload_shape() -> None:
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools)
    requested = runtime.request_shell_approval("python -i", exec_mode="session_start")

    result = approval_resolution_runtime.decide_shell_approval(
        runtime,
        requested.payload["approval_id"],
        approved=True,
        decided_by="tester",
    )

    assert [event.name for event in result["tool_events"]] == ["approval_decision", "shell_start"]
    assert result["tool_events"][-1].payload["session_id"] == "session_1"
    assert result["action_result"]["action"] == "shell_command_start"
    assert result["turn_events"][0]["type"] == "turn.started"
    assert result["turn_events"][-1]["type"] == "turn.completed"
    assert tools.shell_start_calls == ["python -i"]

def test_merge_approval_evidence_refs_deduplicates_and_preserves_ticket_fields() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = runtime.request_gateway_action(
        action_type="demo.noop",
        connector_key="demo_webhook",
        plugin_name="demo_plugin",
        request_payload={"action": "noop"},
        requested_by="workflow.demo",
        trace_id="trace_demo_merge",
        approval_required=True,
        approval_summary="Approve demo noop",
        approval_reason="resolution test",
        metadata={"evidence_refs": ["demo://artifact/1"]},
    )

    merged = approval_ticket_runtime.merge_approval_evidence_refs(
        requested["approval_ticket"],
        ["demo://artifact/1", "demo://artifact/2"],
    )

    assert merged.approval_id == requested["approval_ticket"].approval_id
    assert merged.status == requested["approval_ticket"].status
    assert merged.evidence_refs == ["demo://artifact/1", "demo://artifact/2"]

def test_approval_resolution_response_includes_tool_events_only_when_supplied() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = runtime.request_gateway_action(
        action_type="demo.noop",
        connector_key="demo_webhook",
        plugin_name="demo_plugin",
        request_payload={"action": "noop"},
        requested_by="workflow.demo",
        trace_id="trace_demo_projection",
        approval_required=True,
        approval_summary="Approve demo noop",
        approval_reason="resolution test",
    )
    action_request = requested["action_request"]
    approval_ticket = approval_ticket_runtime.decided_approval_ticket(
        requested["approval_ticket"],
        decision="accept",
        decided_by="tester",
        decision_note="",
        decision_at="2026-04-05T00:00:00+00:00",
    )

    with_events = approval_projection_runtime.approval_resolution_response(
        approval_ticket,
        action_request,
        {"ok": True, "summary": "done"},
        [],
        tool_events=[approval_projection_runtime.approval_decision_event(approval_ticket, action_request)],
    )
    without_events = approval_projection_runtime.approval_resolution_response(
        approval_ticket,
        action_request,
        None,
        [],
    )

    assert [event.name for event in with_events["tool_events"]] == ["approval_decision"]
    assert "tool_events" not in without_events
    assert with_events["turn_events"][0]["type"] == "turn.started"
    assert without_events["turn_events"][-1]["type"] == "turn.completed"


def test_decide_shell_approval_accept_for_session_caches_follow_up() -> None:
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools)
    additional_permissions = {"file_system": {"write": ["/tmp/cache-a"]}}
    requested = runtime.request_shell_approval(
        "python -i",
        exec_mode="session_start",
        sandbox_permissions="with_additional_permissions",
        additional_permissions=additional_permissions,
    )

    result = approval_resolution_runtime.decide_shell_approval(
        runtime,
        requested.payload["approval_id"],
        decision="accept_for_session",
        decided_by="tester",
    )

    assert result["approval_ticket"].decision_type == "accept_for_session"
    assert approval_contract_runtime.shell_approval_is_cached(
        runtime,
        command="python -i",
        cwd=None,
        exec_mode="session_start",
        login=True,
        tty=False,
        shell=None,
        sandbox_permissions="with_additional_permissions",
        additional_permissions=additional_permissions,
    )
    assert (
        approval_contract_runtime.shell_approval_is_cached(
            runtime,
            command="python -i",
            cwd=None,
            exec_mode="session_start",
            login=True,
            tty=False,
            shell=None,
            sandbox_permissions="with_additional_permissions",
            additional_permissions={"file_system": {"write": ["/tmp/cache-b"]}},
        )
        is False
    )


def test_decide_browser_approval_accept_for_session_caches_follow_up_host() -> None:
    runtime = AgentCliRuntime(
        agent=_Agent(),
        browser_action_executor=lambda _: ActionResult(
            ok=True,
            action="browser.navigate",
            summary="browser ok",
            output={"ok": True},
        ),
    )
    requested = runtime.request_gateway_action(
        action_type="browser.navigate",
        connector_key="browser_gateway",
        plugin_name="browser_phase1",
        request_payload={
            "browser_request": {
                "action": "navigate",
                "url": "https://example.com/settings",
            }
        },
        requested_by="workflow.browser",
        trace_id="trace_browser_cache_1",
        approval_summary="Approve browser navigation",
        approval_reason="browser approval required",
    )

    assert requested["approval_ticket"] is not None
    assert approval_contract_runtime.available_decision_types(
        requested["approval_ticket"].available_decisions
    ) == ["accept", "accept_for_session", "decline", "cancel"]

    result = approval_resolution_runtime.decide_gateway_approval(
        runtime,
        requested["approval_ticket"].approval_id,
        decision="accept_for_session",
        decided_by="tester",
    )

    assert result["approval_ticket"].decision_type == "accept_for_session"
    assert approval_contract_runtime.session_approval_is_cached(
        runtime,
        session_cache_keys=approval_contract_runtime.browser_session_cache_keys(host="example.com"),
    )

    follow_up = runtime.request_gateway_action(
        action_type="browser.navigate",
        connector_key="browser_gateway",
        plugin_name="browser_phase1",
        request_payload={
            "browser_request": {
                "action": "navigate",
                "url": "https://example.com/profile",
            }
        },
        requested_by="workflow.browser",
        trace_id="trace_browser_cache_2",
        approval_summary="Approve browser navigation",
        approval_reason="browser approval required",
    )
    other_host = runtime.request_gateway_action(
        action_type="browser.navigate",
        connector_key="browser_gateway",
        plugin_name="browser_phase1",
        request_payload={
            "browser_request": {
                "action": "navigate",
                "url": "https://other.example/profile",
            }
        },
        requested_by="workflow.browser",
        trace_id="trace_browser_cache_3",
        approval_summary="Approve browser navigation",
        approval_reason="browser approval required",
    )

    assert follow_up["approval_ticket"] is None
    assert follow_up["action_request"].approval_required is False
    assert other_host["approval_ticket"] is not None
    assert other_host["action_request"].approval_required is True


def test_request_shell_approval_persists_action_policy_snapshot_into_ticket_metadata() -> None:
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools)

    requested = runtime.request_shell_approval(
        "python -i",
        exec_mode="session_start",
        sandbox_permissions="with_additional_permissions",
        additional_permissions={"file_system": {"write": ["/tmp/out"]}},
        justification="Need writable temp output",
        prefix_rule=["python", "-i"],
    )

    approval_id = str(requested.payload.get("approval_id") or "").strip()
    approval_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    action_request = runtime.gateway_state_store.get_action_request(
        approval_ticket.action_id if approval_ticket is not None else ""
    )

    assert approval_ticket is not None
    assert approval_ticket.metadata["action_policy"]["action_kind"] == "exec_command"
    assert approval_ticket.metadata["action_policy"]["metadata"]["requested_sandbox_permissions"] == (
        "with_additional_permissions"
    )
    assert approval_ticket.metadata["action_policy"]["metadata"]["requested_additional_permissions"] == {
        "file_system": {"write": ["/tmp/out"]}
    }
    assert approval_ticket.metadata["additional_permissions"] == {
        "file_system": {"write": ["/tmp/out"]}
    }
    assert action_request is not None
    assert action_request.payload["justification"] == "Need writable temp output"
    assert action_request.payload["prefix_rule"] == ["python", "-i"]
    assert action_request.payload["additional_permissions"] == {
        "file_system": {"write": ["/tmp/out"]}
    }


def test_request_patch_approval_persists_action_policy_snapshot_into_ticket_metadata(tmp_path: Path) -> None:
    runtime = AgentCliRuntime(agent=_Agent())
    runtime.set_cwd(tmp_path)

    requested = runtime.request_patch_approval(
        """*** Begin Patch
*** Add File: note.txt
+hello
*** End Patch"""
    )

    approval_id = str(requested.payload.get("approval_id") or "").strip()
    approval_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)

    assert approval_ticket is not None
    assert approval_ticket.metadata["action_policy"]["action_kind"] == "apply_patch"
    assert approval_ticket.metadata["action_policy"]["decision"] == "requires_approval"
    assert approval_ticket.metadata["action_policy"]["requirement"] == "needs_approval"


def test_decide_shell_approval_rule_persists_exec_policy_rule(tmp_path: Path) -> None:
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools)
    (tmp_path / ".git").mkdir()
    runtime.set_cwd(tmp_path)
    requested = runtime.request_shell_approval("touch build.log", exec_mode="session_start")

    result = approval_resolution_runtime.decide_shell_approval(
        runtime,
        requested.payload["approval_id"],
        decision="accept_with_execpolicy_amendment",
        decided_by="tester",
    )

    loaded = runtime_exec_policy_rules.load_runtime_exec_policy_rules(cwd=tmp_path)
    assert result["approval_ticket"].decision_type == "accept_with_execpolicy_amendment"
    assert any(rule.decision == "allow" and tuple(rule.command_tokens) == ("touch",) for rule in loaded)

def test_decide_gateway_approval_merges_github_artifacts_via_gateway_seam() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = runtime.request_gateway_action(
        action_type="github.workflow.dispatch",
        connector_key="github_webhook",
        plugin_name="github_phase1",
        request_payload={"action": "dispatch", "workflow": "build.yml"},
        requested_by="workflow.demo",
        trace_id="trace_demo_github",
        approval_required=True,
        approval_summary="Approve workflow dispatch",
        approval_reason="resolution test",
        metadata={"evidence_refs": ["demo://existing"]},
    )
    existing_refs = list(requested["approval_ticket"].evidence_refs)

    result = approval_resolution_runtime.decide_gateway_approval(
        runtime,
        requested["approval_ticket"].approval_id,
        approved=True,
        decided_by="tester",
        github_action_artifact_refs_fn=lambda **_: {
            "artifact_refs": ["https://artifacts.example/run/1"],
            "details": {"count": 1},
        },
        find_github_workflow_run_fn=lambda **_: {"html_url": "https://github.example/runs/99"},
    )

    assert result["approval_ticket"].evidence_refs == existing_refs + [
        "https://artifacts.example/run/1",
        "https://github.example/runs/99",
    ]
    assert result["audit_records"][1].details["artifact_refs"] == [
        "https://artifacts.example/run/1",
        "https://github.example/runs/99",
    ]
    assert result["audit_records"][1].details["github_artifacts"] == {"count": 1}
    assert result["audit_records"][1].details["github_workflow_run"] == {
        "html_url": "https://github.example/runs/99"
    }

def test_decide_gateway_approval_updates_browser_workflow_terminal_state() -> None:
    runtime = AgentCliRuntime(
        agent=_Agent(),
        browser_action_executor=lambda _: ActionResult(
            ok=True,
            action="browser.navigate",
            summary="browser ok",
            output={"screenshot": {"path": "/tmp/browser.png"}},
        ),
    )
    runtime.gateway_state_store.save_workflow_run(
        WorkflowRun(
            workflow_run_id="wf_browser_1",
            workflow_name="browser-demo",
            plugin_name="browser_phase1",
            trace_id="trace_browser_1",
            status="running",
            started_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:00+00:00",
            current_step="awaiting_approval",
            context={},
        )
    )
    requested = runtime.request_gateway_action(
        action_type="browser.navigate",
        connector_key="browser_gateway",
        plugin_name="browser_phase1",
        request_payload={"browser_request": {"action": "navigate", "url": "https://example.com"}},
        requested_by="workflow.browser",
        trace_id="trace_browser_1",
        workflow_run_id="wf_browser_1",
        approval_required=True,
        approval_summary="Approve browser action",
        approval_reason="resolution test",
    )

    result = approval_resolution_runtime.decide_gateway_approval(
        runtime,
        requested["approval_ticket"].approval_id,
        approved=True,
        decided_by="tester",
    )

    workflow_run = runtime.gateway_state_store.get_workflow_run("wf_browser_1")

    assert result["approval_ticket"].evidence_refs == ["/tmp/browser.png"]
    assert workflow_run is not None
    assert workflow_run.status == "ok"
    assert workflow_run.current_step == "browser_action_executed"
    assert workflow_run.result_summary == "browser ok"
    assert workflow_run.context["browser_workflow"]["status"] == "completed"
    assert workflow_run.context["browser_workflow"]["last_execution"]["artifact_refs"] == [
        "/tmp/browser.png"
    ]
    assert workflow_run.context["workflow_result"]["evidence_refs"] == ["/tmp/browser.png"]


def test_mcp_tool_approval_ticket_aligns_with_local_shell_ticket_key_fields() -> None:
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools)
    shell_event = runtime.request_shell_approval("echo hi", exec_mode="session_start")
    shell_approval_id = str(shell_event.payload.get("approval_id") or "").strip()
    shell_ticket = runtime.gateway_state_store.get_approval_ticket(shell_approval_id)
    assert shell_ticket is not None

    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_ticket_1",
        approval_required=True,
        approval_summary="Approve MCP tool call mcp__atlas__search_docs",
        approval_reason="mcp approval required",
    )
    mcp_ticket = requested["approval_ticket"]
    assert mcp_ticket is not None

    for field in ("approval_id", "action_id", "trace_id", "status", "requested_by", "summary", "reason"):
        assert str(getattr(shell_ticket, field) or "").strip()
        assert str(getattr(mcp_ticket, field) or "").strip()
    assert shell_ticket.status == "pending"
    assert mcp_ticket.status == "pending"
    assert str(shell_ticket.metadata.get("source_action_type") or "").strip() == "shell_command"
    assert str(mcp_ticket.metadata.get("source_action_type") or "").strip() == "mcp.tool.call"


def test_decide_gateway_approval_executes_mcp_tool_call_and_keeps_audit_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_approve_1",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval(
        runtime,
        requested["approval_ticket"].approval_id,
        approved=True,
        decided_by="tester",
    )

    assert mcp_runtime.calls == [
        {
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
        }
    ]
    assert result["approval_ticket"].status == "approved"
    assert result["action_result"].ok is True
    assert result["action_result"].action == "mcp.tool.call"
    assert result["action_result"].output["projected_name"] == "mcp__atlas__search_docs"
    assert result["audit_records"][0].stage == "approval"
    assert result["audit_records"][0].status == "approved"
    assert result["audit_records"][1].stage == "action_execute"
    assert result["audit_records"][1].status == "ok"
    assert result["audit_records"][1].approval_id == result["approval_ticket"].approval_id
    assert result["audit_records"][1].details["decision_outcome"] == "approved"
    execution_contract = result["audit_records"][1].details["execution_contract"]
    assert execution_contract["source"] == "mcp"
    assert execution_contract["tool_family"] == "mcp_tool_call"
    assert execution_contract["action_family"] == "mcp"
    assert execution_contract["action_type"] == "mcp.tool.call"
    assert execution_contract["decision_outcome"] == "approved"
    assert execution_contract["approval_required"] is True
    assert execution_contract["requires_confirmation"] is True


def test_decide_gateway_approval_reject_for_mcp_keeps_ticket_and_audit_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_reject_1",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="rejected",
        decided_by="tester",
    )

    assert mcp_runtime.calls == []
    assert result["decision_outcome"] == "rejected"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_by == "tester"
    assert result["approval_ticket"].decision_note == "approval rejected"
    assert result.get("action_result") is None
    assert len(result["audit_records"]) == 1
    assert result["audit_records"][0].stage == "approval"
    assert result["audit_records"][0].status == "rejected"
    assert result["audit_records"][0].approval_id == result["approval_ticket"].approval_id


def test_decide_gateway_approval_timeout_for_mcp_maps_to_rejected_with_stable_note_and_audit() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_timeout_1",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_timeout(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_timeout",
    )

    assert mcp_runtime.calls == []
    assert result["decision_outcome"] == "timed_out"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_by == "system_timeout"
    assert result["approval_ticket"].decision_note == "approval timeout"
    assert result.get("action_result") is None
    assert len(result["audit_records"]) == 1
    assert result["audit_records"][0].stage == "approval"
    assert result["audit_records"][0].status == "rejected"
    assert result["audit_records"][0].summary.startswith("rejected")


def test_decide_gateway_approval_expired_for_mcp_maps_to_rejected_with_expired_outcome_and_note() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_expired_1",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_expired(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_gc",
    )

    assert mcp_runtime.calls == []
    assert result["decision_outcome"] == "expired"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_by == "system_gc"
    assert result["approval_ticket"].decision_note == "approval expired"
    assert result.get("action_result") is None
    assert len(result["audit_records"]) == 1
    assert result["audit_records"][0].stage == "approval"
    assert result["audit_records"][0].status == "rejected"


def test_decide_gateway_approval_with_outcome_preserves_custom_note_for_timeout_paths() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "policy"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_custom_note_1",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="timeout",
        decided_by="system_timeout",
        decision_note="expired by operator SLA",
    )

    assert result["decision_outcome"] == "timed_out"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_note == "expired by operator SLA"


def test_gateway_approval_decision_note_guard_defaults_and_overrides() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())

    scenarios = [
        {
            "label": "rejected_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "expected_outcome": "rejected",
            "expected_note": "approval rejected",
        },
        {
            "label": "rejected_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
                decision_note="rejected by policy guard",
            ),
            "expected_outcome": "rejected",
            "expected_note": "rejected by policy guard",
        },
        {
            "label": "timeout_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "expected_outcome": "timed_out",
            "expected_note": "approval timeout",
        },
        {
            "label": "timeout_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
                decision_note="timeout by external watchdog",
            ),
            "expected_outcome": "timed_out",
            "expected_note": "timeout by external watchdog",
        },
        {
            "label": "expired_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "expected_outcome": "expired",
            "expected_note": "approval expired",
        },
        {
            "label": "expired_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
                decision_note="expired by lease GC",
            ),
            "expected_outcome": "expired",
            "expected_note": "expired by lease GC",
        },
    ]

    for case in scenarios:
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key="mcp:atlas",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": "mcp__atlas__search_docs",
                "arguments": {"query": case["label"]},
                "tool_contract": {
                    "name": "mcp__atlas__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": "mcp.server:atlas",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_decision_note_guard_{case['label']}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        result = case["invoke"](requested["approval_ticket"].approval_id)
        assert result["decision_outcome"] == case["expected_outcome"], case["label"]
        assert result["approval_ticket"].status == "rejected", case["label"]
        assert result["approval_ticket"].decision_note == case["expected_note"], case["label"]


def test_gateway_approval_decision_note_defaults_and_overrides_matrix_guard() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())

    scenarios = [
        {
            "label": "rejected_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "expected_outcome": "rejected",
            "expected_note": "approval rejected",
        },
        {
            "label": "rejected_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
                decision_note="rejected by custom policy guard",
            ),
            "expected_outcome": "rejected",
            "expected_note": "rejected by custom policy guard",
        },
        {
            "label": "timed_out_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "expected_outcome": "timed_out",
            "expected_note": "approval timeout",
        },
        {
            "label": "timed_out_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
                decision_note="timeout note from watchdog",
            ),
            "expected_outcome": "timed_out",
            "expected_note": "timeout note from watchdog",
        },
        {
            "label": "expired_default",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "expected_outcome": "expired",
            "expected_note": "approval expired",
        },
        {
            "label": "expired_custom",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
                decision_note="expired note from lease collector",
            ),
            "expected_outcome": "expired",
            "expected_note": "expired note from lease collector",
        },
    ]

    for case in scenarios:
        requested = _request_mcp_gateway_action(runtime, label=f"decision_note_matrix_{case['label']}")
        result = case["invoke"](requested["approval_ticket"].approval_id)

        assert result["decision_outcome"] == case["expected_outcome"], case["label"]
        assert result["approval_ticket"].status == "rejected", case["label"]
        assert result["approval_ticket"].decision_note == case["expected_note"], case["label"]
        assert result.get("action_result") is None, case["label"]

        approval_audit = next(item for item in result["audit_records"] if item.stage == "approval")
        details = dict(approval_audit.details or {})
        assert approval_audit.status == "rejected", case["label"]
        assert details["decision_outcome"] == case["expected_outcome"], case["label"]
        assert details["decision_note"] == case["expected_note"], case["label"]
        assert details["execution_skipped"] is True, case["label"]


def test_gateway_approval_response_notes_and_outcomes_stay_synced() -> None:
    rejected_decision = partial(
        approval_resolution_runtime.decide_gateway_approval_with_outcome,
        outcome="rejected",
        decided_by="tester",
    )
    timeout_decision = partial(
        approval_resolution_runtime.decide_gateway_approval_timeout,
        decided_by="system_timeout",
    )
    expired_decision = partial(
        approval_resolution_runtime.decide_gateway_approval_expired,
        decided_by="system_gc",
    )

    cases = [
        {
            "label": "rejected_default",
            "decision_fn": rejected_decision,
            "note_input": "",
            "expected_outcome": "rejected",
            "expected_note": "approval rejected",
        },
        {
            "label": "rejected_custom",
            "decision_fn": rejected_decision,
            "note_input": "rejected by policy guard",
            "expected_outcome": "rejected",
            "expected_note": "rejected by policy guard",
        },
        {
            "label": "timeout_default",
            "decision_fn": timeout_decision,
            "note_input": "",
            "expected_outcome": "timed_out",
            "expected_note": "approval timeout",
        },
        {
            "label": "timeout_custom",
            "decision_fn": timeout_decision,
            "note_input": "timeout by external watchdog",
            "expected_outcome": "timed_out",
            "expected_note": "timeout by external watchdog",
        },
        {
            "label": "expired_default",
            "decision_fn": expired_decision,
            "note_input": "",
            "expected_outcome": "expired",
            "expected_note": "approval expired",
        },
        {
            "label": "expired_custom",
            "decision_fn": expired_decision,
            "note_input": "expired by lease GC",
            "expected_outcome": "expired",
            "expected_note": "expired by lease GC",
        },
    ]

    for case in cases:
        runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key="mcp:atlas",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": "mcp__atlas__search_docs",
                "arguments": {"query": case["label"]},
                "tool_contract": {
                    "name": "mcp__atlas__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": "mcp.server:atlas",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_note_outcome_sync_{case['label']}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        result = case["decision_fn"](
            runtime,
            requested["approval_ticket"].approval_id,
            decision_note=case["note_input"],
        )
        assert result["decision_outcome"] == case["expected_outcome"], case["label"]
        assert result["approval_ticket"].status == "rejected", case["label"]
        assert result["approval_ticket"].decision_note == case["expected_note"], case["label"]


def test_gateway_execution_decision_outcome_projection_timeout_note_maps_to_timed_out() -> None:
    ticket = type("Ticket", (), {"status": "rejected", "decision_note": "approval timeout"})()
    outcome = approval_resolution_gateway_runtime._decision_outcome_from_approval_ticket(ticket)
    assert outcome == "timed_out"


def test_gateway_execution_decision_outcome_projection_expired_note_maps_to_expired() -> None:
    ticket = type("Ticket", (), {"status": "rejected", "decision_note": "approval expired"})()
    outcome = approval_resolution_gateway_runtime._decision_outcome_from_approval_ticket(ticket)
    assert outcome == "expired"


def test_gateway_execution_decision_outcome_projection_rejected_without_special_note_stays_rejected() -> None:
    ticket = type("Ticket", (), {"status": "rejected", "decision_note": ""})()
    outcome = approval_resolution_gateway_runtime._decision_outcome_from_approval_ticket(ticket)
    assert outcome == "rejected"


def test_mcp_gateway_approval_outcome_matrix_guard_table_driven() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime

    scenarios = [
        {
            "label": "approved",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="approved",
                decided_by="tester",
            ),
            "expected_ticket_status": "approved",
            "expected_outcome": "approved",
            "expected_note": None,
            "expect_action_execute_audit": True,
            "expected_execution_contract_outcome": "approved",
            "expected_mcp_call_count_delta": 1,
            "expected_execution_skipped": False,
        },
        {
            "label": "rejected",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "expected_ticket_status": "rejected",
            "expected_outcome": "rejected",
            "expected_note": "approval rejected",
            "expect_action_execute_audit": False,
            "expected_execution_contract_outcome": None,
            "expected_mcp_call_count_delta": 0,
            "expected_execution_skipped": True,
        },
        {
            "label": "timed_out",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "expected_ticket_status": "rejected",
            "expected_outcome": "timed_out",
            "expected_note": "approval timeout",
            "expect_action_execute_audit": False,
            "expected_execution_contract_outcome": None,
            "expected_mcp_call_count_delta": 0,
            "expected_execution_skipped": True,
        },
        {
            "label": "expired",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "expected_ticket_status": "rejected",
            "expected_outcome": "expired",
            "expected_note": "approval expired",
            "expect_action_execute_audit": False,
            "expected_execution_contract_outcome": None,
            "expected_mcp_call_count_delta": 0,
            "expected_execution_skipped": True,
        },
    ]

    for case in scenarios:
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key="mcp:atlas",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": "mcp__atlas__search_docs",
                "arguments": {"query": case["label"]},
                "tool_contract": {
                    "name": "mcp__atlas__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": "mcp.server:atlas",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_outcome_matrix_{case['label']}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        approval_id = requested["approval_ticket"].approval_id
        calls_before = len(mcp_runtime.calls)
        result = case["invoke"](approval_id)

        assert result["decision_outcome"] == case["expected_outcome"], case["label"]
        assert result["approval_ticket"].status == case["expected_ticket_status"], case["label"]
        if case["expected_note"] is None:
            assert result["approval_ticket"].decision_note in {None, ""}, case["label"]
        else:
            assert result["approval_ticket"].decision_note == case["expected_note"], case["label"]

        approval_audits = [item for item in result["audit_records"] if item.stage == "approval"]
        assert len(approval_audits) == 1, case["label"]
        assert approval_audits[0].details["decision_outcome"] == case["expected_outcome"], case["label"]
        assert approval_audits[0].details["execution_skipped"] is case["expected_execution_skipped"], case["label"]

        action_execute_audits = [item for item in result["audit_records"] if item.stage == "action_execute"]
        if case["expect_action_execute_audit"]:
            assert len(action_execute_audits) == 1, case["label"]
            assert (
                action_execute_audits[0].details["execution_contract"]["decision_outcome"]
                == case["expected_execution_contract_outcome"]
            ), case["label"]
        else:
            assert action_execute_audits == [], case["label"]

        calls_after = len(mcp_runtime.calls)
        assert calls_after - calls_before == case["expected_mcp_call_count_delta"], case["label"]


def test_mcp_gateway_approval_outcome_matrix_guard_visible_field_contracts() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    scenarios = [
        (
            "approved",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="approved",
                decided_by="tester",
            ),
            False,
        ),
        (
            "rejected",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            True,
        ),
        (
            "timed_out",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            True,
        ),
        (
            "expired",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            True,
        ),
    ]

    for expected_outcome, decide_fn, expected_execution_skipped in scenarios:
        requested = _request_mcp_gateway_action(runtime, label=f"visible_contract_{expected_outcome}")
        result = decide_fn(requested["approval_ticket"].approval_id)
        assert result["decision_outcome"] == expected_outcome, expected_outcome

        approval_audit = next(item for item in result["audit_records"] if item.stage == "approval")
        details = dict(approval_audit.details or {})
        assert details["decision_outcome"] == expected_outcome, expected_outcome
        assert details["execution_skipped"] is expected_execution_skipped, expected_outcome
        assert "decision_note" in details, expected_outcome
        assert "decided_by" in details, expected_outcome

        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        if expected_execution_skipped:
            assert action_execute == [], expected_outcome
        else:
            assert len(action_execute) == 1, expected_outcome
            contract = dict(action_execute[0].details.get("execution_contract") or {})
            assert contract["decision_outcome"] == expected_outcome, expected_outcome


def test_mcp_gateway_approval_outcome_matrix_guard_explicit_visible_response_fields() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    scenarios = [
        (
            "approved",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="approved",
                decided_by="tester",
            ),
            "approved",
            None,
            1,
            False,
        ),
        (
            "rejected",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "rejected",
            "approval rejected",
            0,
            True,
        ),
        (
            "timed_out",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "rejected",
            "approval timeout",
            0,
            True,
        ),
        (
            "expired",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "rejected",
            "approval expired",
            0,
            True,
        ),
    ]

    for expected_outcome, decide_fn, expected_ticket_status, expected_note, expected_call_delta, expected_execution_skipped in scenarios:
        requested = _request_mcp_gateway_action(runtime, label=f"matrix_visible_{expected_outcome}")
        calls_before = len(mcp_runtime.calls)
        result = decide_fn(requested["approval_ticket"].approval_id)
        calls_after = len(mcp_runtime.calls)

        assert result["decision_outcome"] == expected_outcome, expected_outcome
        assert result["approval_ticket"].status == expected_ticket_status, expected_outcome
        if expected_note is None:
            assert result["approval_ticket"].decision_note in {None, ""}, expected_outcome
        else:
            assert result["approval_ticket"].decision_note == expected_note, expected_outcome
        assert calls_after - calls_before == expected_call_delta, expected_outcome

        turn_events = list(result["turn_events"])
        item_events = list(result["item_events"])
        assert turn_events[0]["type"] == "turn.started", expected_outcome
        assert turn_events[-1]["type"] == "turn.completed", expected_outcome
        assert len(turn_events) == len(item_events) + 2, expected_outcome
        if expected_outcome == "approved":
            event_types = [str(event.get("type") or "") for event in item_events]
            assert event_types[:2] == ["item.started", "item.completed"], expected_outcome
            assert len(item_events) >= 4, expected_outcome
            assert all(item_type in {"item.started", "item.completed"} for item_type in event_types), expected_outcome
            completed_tools = [
                str(event.get("item", {}).get("tool") or "")
                for event in item_events
                if str(event.get("type") or "") == "item.completed"
            ]
            assert "approval_decision" in completed_tools, expected_outcome
            assert any(tool in {"gateway_action_execute", "mcp_tool_call"} for tool in completed_tools), expected_outcome
        else:
            _assert_decision_event_shape(result)
        approval_audit = next(item for item in result["audit_records"] if item.stage == "approval")
        details = dict(approval_audit.details or {})
        assert details["decision_outcome"] == expected_outcome, expected_outcome
        assert details["execution_skipped"] is expected_execution_skipped, expected_outcome
        assert str(details.get("decided_by") or "").strip(), expected_outcome
        assert "decision_note" in details, expected_outcome

        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        if expected_outcome == "approved":
            assert len(action_execute) == 1, expected_outcome
            execution_contract = dict(action_execute[0].details.get("execution_contract") or {})
            assert execution_contract["decision_outcome"] == "approved", expected_outcome
            assert execution_contract["tool_family"] == "mcp_tool_call", expected_outcome
            assert result.get("action_result") is not None, expected_outcome
        else:
            assert action_execute == [], expected_outcome
            assert result.get("action_result") is None, expected_outcome


def test_mcp_gateway_approval_audit_observability_contract_matrix_guard() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime
    scenarios = [
        (
            "approved",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="approved",
                decided_by="tester",
            ),
            "action.executed",
        ),
        (
            "rejected",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "gateway.action.skipped",
        ),
        (
            "timed_out",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "gateway.action.skipped",
        ),
        (
            "expired",
            lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "gateway.action.skipped",
        ),
    ]

    for expected_outcome, decide_fn, expected_terminal_event in scenarios:
        requested = _request_mcp_gateway_action(runtime, label=f"audit_observability_{expected_outcome}")
        result = decide_fn(requested["approval_ticket"].approval_id)

        assert approval_resolution_gateway_runtime._decision_outcome_from_approval_ticket(result["approval_ticket"]) == expected_outcome
        approval_audit = next(item for item in result["audit_records"] if item.stage == "approval")
        details = dict(approval_audit.details or {})
        observability = dict(details.get("observability") or {})
        reason_codes = dict(details.get("reason_codes") or {})
        decision_trace = list(details.get("decision_trace") or [])

        assert details["schema_version"] == 1, expected_outcome
        assert details["decision_outcome"] == expected_outcome, expected_outcome
        assert details["reason_code"] == f"approval.{expected_outcome}", expected_outcome
        assert reason_codes["pending"] == "approval.pending", expected_outcome
        assert reason_codes["approved"] == "approval.approved", expected_outcome
        assert reason_codes["rejected"] == "approval.rejected", expected_outcome
        assert reason_codes["timed_out"] == "approval.timed_out", expected_outcome
        assert reason_codes["expired"] == "approval.expired", expected_outcome
        assert details["latency_bucket_field"] == "approval_latency_bucket", expected_outcome
        assert details["latency_bucket"] in {
            "lt_100ms",
            "100ms_500ms",
            "500ms_1s",
            "1s_5s",
            "ge_5s",
            "unknown",
        }, expected_outcome
        if "latency_ms" in details:
            assert isinstance(details["latency_ms"], int), expected_outcome
            assert details["latency_ms"] >= 0, expected_outcome
        assert decision_trace == [
            "approval.requested",
            f"approval.{expected_outcome}",
            expected_terminal_event,
        ], expected_outcome

        snapshot = dict(details.get("tool_snapshot") or {})
        assert snapshot["projected_name"] == "mcp__atlas__search_docs", expected_outcome
        assert snapshot["connector_key"] == "mcp:atlas", expected_outcome
        assert snapshot["approval_scope"] == "mcp.server:atlas", expected_outcome

        assert observability["schema_version"] == 1, expected_outcome
        assert observability["reason_code"] == details["reason_code"], expected_outcome
        assert observability["decision_trace"] == decision_trace, expected_outcome
        assert observability["latency_bucket_field"] == details["latency_bucket_field"], expected_outcome
        assert observability["latency_bucket"] == details["latency_bucket"], expected_outcome
        assert dict(observability["reason_codes"]) == reason_codes, expected_outcome
        assert dict(observability["tool_snapshot"]) == snapshot, expected_outcome


def test_normalized_gateway_outcome_covers_synonyms_and_errors() -> None:
    test_vectors = {
        " ApproVE ": "approved",
        "allow": "approved",
        "DENY": "rejected",
        "timed-out": "timed_out",
        "TiMeD_Out": "timed_out",
        "TIMEOUT": "timed_out",
        "expired": "expired",
        "expire": "expired",
    }

    for provided, expected in test_vectors.items():
        assert approval_resolution_runtime._normalized_gateway_outcome(provided) == expected

    with pytest.raises(ValueError, match=r"unsupported gateway approval outcome: unsupported_outcome"):
        approval_resolution_runtime._normalized_gateway_outcome("unsupported_outcome")


def test_decide_gateway_approval_with_outcome_reject_timeout_expired_audit_guard() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())

    scenarios = [
        {"input": "deny", "expected_outcome": "rejected", "expected_note": "approval rejected"},
        {"input": "timed-out", "expected_outcome": "timed_out", "expected_note": "approval timeout"},
        {"input": "EXPIRED", "expected_outcome": "expired", "expected_note": "approval expired"},
    ]

    for case in scenarios:
        requested = _request_mcp_gateway_action(runtime, label=case["input"])
        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome=case["input"],
            decided_by="tester",
        )

        assert result["decision_outcome"] == case["expected_outcome"]
        assert result["approval_ticket"].status == "rejected"
        assert result["approval_ticket"].decision_note == case["expected_note"]
        assert result.get("action_result") is None
        assert len(result["audit_records"]) == 1
        audit_record = result["audit_records"][0]
        assert audit_record.stage == "approval"
        assert audit_record.status == "rejected"
        assert audit_record.details["decision_outcome"] == case["expected_outcome"]
        assert audit_record.details["execution_skipped"] is True
        assert audit_record.details["decision_note"] == case["expected_note"]
        assert audit_record.details["decided_by"] == "tester"


def test_decide_gateway_approval_with_outcome_approved_projects_audit_outcome_and_execution_flag() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    requested = _request_mcp_gateway_action(runtime, label="approved_guard")

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )

    assert result["decision_outcome"] == "approved"
    assert result["approval_ticket"].status == "approved"
    assert result["action_result"].ok is True
    approval_audit = result["audit_records"][0]
    assert approval_audit.stage == "approval"
    assert approval_audit.details["decision_outcome"] == "approved"
    assert approval_audit.details["execution_skipped"] is False


@pytest.mark.parametrize(
    "decision_fn,expected_outcome",
    [
        (
            lambda runtime, approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "rejected",
        ),
        (
            lambda runtime, approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "timed_out",
        ),
        (
            lambda runtime, approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
            "expired",
        ),
    ],
    ids=["rejected", "timeout", "expired"],
)
def test_reject_timeout_expired_decisions_preserve_turn_and_item_event_shape(
    decision_fn,
    expected_outcome,
) -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = _request_mcp_gateway_action(runtime, label="shape_guard")

    result = decision_fn(runtime, requested["approval_ticket"].approval_id)

    assert result.get("action_result") is None
    assert result["decision_outcome"] == expected_outcome
    assert result["approval_ticket"].status == "rejected"
    _assert_decision_event_shape(result)


def test_gateway_execution_contract_matrix_guard_for_mcp_outcomes() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime

    scenarios = [
        {
            "label": "approved",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="approved",
                decided_by="tester",
            ),
            "expect_action_execute": True,
            "expected_contract": {
                "source": "mcp",
                "tool_family": "mcp_tool_call",
                "action_family": "mcp",
                "action_type": "mcp.tool.call",
                "decision_outcome": "approved",
                "approval_required": True,
                "requires_confirmation": True,
            },
        },
        {
            "label": "rejected",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
            "expect_action_execute": False,
            "expected_contract": None,
        },
        {
            "label": "timed_out",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
            "expect_action_execute": False,
            "expected_contract": None,
        },
    ]

    for case in scenarios:
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key="mcp:atlas",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": "mcp__atlas__search_docs",
                "arguments": {"query": case["label"]},
                "tool_contract": {
                    "name": "mcp__atlas__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": "mcp.server:atlas",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_gateway_contract_guard_{case['label']}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )

        result = case["invoke"](requested["approval_ticket"].approval_id)
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]

        if case["expect_action_execute"]:
            assert len(action_execute) == 1, case["label"]
            contract = action_execute[0].details["execution_contract"]
            for key, value in dict(case["expected_contract"] or {}).items():
                assert contract.get(key) == value, f"{case['label']}:{key}"
            assert action_execute[0].details["decision_outcome"] == "approved", case["label"]
        else:
            assert action_execute == [], case["label"]


def test_mcp_execution_contract_flag_guard_on_approved_path() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "flag_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_execution_contract_flag_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )

    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    contract = action_execute[0].details["execution_contract"]
    assert contract["decision_outcome"] == "approved"
    assert contract["approval_required"] is True
    assert contract["requires_confirmation"] is True
    assert contract["mutates_ui"] is False
    assert isinstance(contract["approval_required"], bool)
    assert isinstance(contract["requires_confirmation"], bool)
    assert isinstance(contract["mutates_ui"], bool)


def test_mcp_outcome_boolean_contract_guard_non_approved_paths() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    mcp_runtime = _McpRuntimeStub()
    runtime._mcp_runtime = mcp_runtime

    scenarios = [
        {
            "label": "rejected",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_with_outcome(
                runtime,
                approval_id,
                outcome="rejected",
                decided_by="tester",
            ),
        },
        {
            "label": "timed_out",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_timeout(
                runtime,
                approval_id,
                decided_by="system_timeout",
            ),
        },
        {
            "label": "expired",
            "invoke": lambda approval_id: approval_resolution_runtime.decide_gateway_approval_expired(
                runtime,
                approval_id,
                decided_by="system_gc",
            ),
        },
    ]

    for case in scenarios:
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key="mcp:atlas",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": "mcp__atlas__search_docs",
                "arguments": {"query": case["label"]},
                "tool_contract": {
                    "name": "mcp__atlas__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": "mcp.server:atlas",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_boolean_guard_{case['label']}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        calls_before = len(mcp_runtime.calls)
        result = case["invoke"](requested["approval_ticket"].approval_id)
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]

        assert result["approval_ticket"].status == "rejected", case["label"]
        assert result.get("action_result") is None, case["label"]
        assert action_execute == [], case["label"]
        assert len(mcp_runtime.calls) == calls_before, case["label"]


def test_mcp_guard_combined_assertions_keep_runtime_execution_vector_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "combined_assertions"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "source": "mcp",
                "approval_required": True,
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
                "requires_confirmation": True,
                "mutates_ui": False,
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_combined_assertions_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )

    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details
    contract = details["execution_contract"]

    assert details["decision_outcome"] == "approved"
    assert contract["source"] == "mcp"
    assert contract["decision_outcome"] == "approved"
    assert contract["approval_required"] is True
    assert contract["requires_confirmation"] is True
    assert contract["mutates_ui"] is False
    assert isinstance(contract["approval_required"], bool)
    assert isinstance(contract["requires_confirmation"], bool)
    assert isinstance(contract["mutates_ui"], bool)
    assert details["mcp_execution"]["approval"] == {
        "required": True,
        "family": "mcp_tool_call",
        "scope": "mcp.server:atlas",
    }


def test_mcp_contract_scope_guard_keeps_request_and_execution_scopes_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_scope = "mcp.server:atlas"
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "scope_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": "mcp_tool_call",
                "approval_scope": expected_scope,
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_scope_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1

    request_scope = requested["action_request"].payload["tool_contract"]["approval_scope"]
    runtime_scope = action_execute[0].details["mcp_execution"]["approval"]["scope"]
    connector_key = action_execute[0].details["execution_contract"]["connector_key"]

    assert request_scope == expected_scope
    assert runtime_scope == expected_scope
    assert connector_key == "mcp:atlas"
    assert runtime_scope == f"mcp.server:{connector_key.split(':', 1)[1]}"


def test_mcp_scope_derivation_guard_from_connector_key_matrix() -> None:
    class _DerivedScopeMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _DerivedScopeMcpRuntimeStub()

    scenarios = [
        {"server_name": "atlas"},
        {"server_name": "atlas_prod"},
        {"server_name": "team42"},
    ]
    for case in scenarios:
        server_name = case["server_name"]
        connector_key = f"mcp:{server_name}"
        expected_scope = f"mcp.server:{server_name}"
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=connector_key,
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"scope-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": expected_scope,
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_scope_derivation_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )

        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        assert details["execution_contract"]["connector_key"] == connector_key, server_name
        assert requested["action_request"].payload["tool_contract"]["approval_scope"] == expected_scope, server_name
        assert details["mcp_execution"]["approval"]["scope"] == expected_scope, server_name
        assert details["mcp_execution"]["approval"]["scope"] == f"mcp.server:{connector_key.split(':', 1)[1]}", server_name


def test_mcp_connector_key_format_guard_matrix() -> None:
    class _ConnectorKeyAwareMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _ConnectorKeyAwareMcpRuntimeStub()

    scenarios = [
        {"server_name": "atlas"},
        {"server_name": "atlas_prod"},
        {"server_name": "team-42"},
    ]
    for case in scenarios:
        server_name = case["server_name"]
        expected_connector_key = f"mcp:{server_name}"
        expected_scope = f"mcp.server:{server_name}"
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=expected_connector_key,
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"connector-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_family": "mcp_tool_call",
                    "approval_scope": expected_scope,
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_connector_key_format_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )

        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        connector_key = str(details["execution_contract"]["connector_key"] or "")
        derived_server = connector_key.split(":", 1)[1] if ":" in connector_key else ""

        assert connector_key == expected_connector_key, server_name
        assert connector_key.startswith("mcp:"), server_name
        assert connector_key.count(":") == 1, server_name
        assert connector_key.strip() == connector_key, server_name
        assert derived_server == server_name, server_name
        assert str(details["mcp_execution"]["server_name"] or "") == server_name, server_name
        assert details["mcp_execution"]["approval"]["scope"] == expected_scope, server_name
        assert details["mcp_execution"]["approval"]["scope"] == f"mcp.server:{derived_server}", server_name


def test_mcp_approval_family_guard_keeps_request_and_execution_family_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_family = "mcp_tool_call"
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "family_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_family": expected_family,
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_approval_family_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    assert requested["action_request"].payload["tool_contract"]["approval_family"] == expected_family
    assert details["mcp_execution"]["approval"]["family"] == expected_family
    assert details["execution_contract"]["tool_family"] == expected_family


def test_mcp_approval_required_guard_keeps_request_and_execution_required_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_required = True
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "required_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "approval_required": expected_required,
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_approval_required_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    request_required = requested["action_request"].payload["tool_contract"]["approval_required"]
    execution_required = details["execution_contract"]["approval_required"]
    runtime_required = details["mcp_execution"]["approval"]["required"]

    assert request_required is expected_required
    assert execution_required is expected_required
    assert runtime_required is expected_required
    assert isinstance(request_required, bool)
    assert isinstance(execution_required, bool)
    assert isinstance(runtime_required, bool)


def test_mcp_requires_confirmation_guard_keeps_request_and_execution_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_confirmation = True
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "confirmation_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "requires_confirmation": expected_confirmation,
                "approval_required": True,
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_requires_confirmation_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    request_confirmation = requested["action_request"].payload["tool_contract"]["requires_confirmation"]
    execution_confirmation = details["execution_contract"]["requires_confirmation"]
    assert request_confirmation is expected_confirmation
    assert execution_confirmation is expected_confirmation
    assert isinstance(request_confirmation, bool)
    assert isinstance(execution_confirmation, bool)


def test_mcp_mutates_ui_guard_keeps_request_and_execution_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_mutates_ui = False
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "mutates_ui_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "mutates_ui": expected_mutates_ui,
                "requires_confirmation": True,
                "approval_required": True,
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_mutates_ui_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    request_mutates_ui = requested["action_request"].payload["tool_contract"]["mutates_ui"]
    execution_mutates_ui = details["execution_contract"]["mutates_ui"]
    assert request_mutates_ui is expected_mutates_ui
    assert execution_mutates_ui is expected_mutates_ui
    assert isinstance(request_mutates_ui, bool)
    assert isinstance(execution_mutates_ui, bool)


def test_mcp_source_tool_family_guard_keeps_request_and_execution_consistent() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_source = "mcp"
    expected_tool_family = "mcp_tool_call"
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "source_family_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "source": expected_source,
                "tool_family": expected_tool_family,
                "mutates_ui": False,
                "requires_confirmation": True,
                "approval_required": True,
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_source_tool_family_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    request_contract = requested["action_request"].payload["tool_contract"]
    execution_contract = details["execution_contract"]
    assert request_contract["source"] == expected_source
    assert request_contract["tool_family"] == expected_tool_family
    assert execution_contract["source"] == expected_source
    assert execution_contract["tool_family"] == expected_tool_family


def test_mcp_family_mapping_guard_maps_request_remote_family_to_execution_call_family() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "family_mapping_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "source": "mcp",
                "tool_family": "mcp_remote",
                "approval_family": "mcp_tool_call",
                "approval_scope": "mcp.server:atlas",
                "approval_required": True,
                "requires_confirmation": True,
                "mutates_ui": False,
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_family_mapping_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details

    request_contract = requested["action_request"].payload["tool_contract"]
    execution_contract = details["execution_contract"]
    assert request_contract["tool_family"] == "mcp_remote"
    assert request_contract["approval_family"] == "mcp_tool_call"
    assert execution_contract["tool_family"] == "mcp_tool_call"
    assert details["mcp_execution"]["approval"]["family"] == "mcp_tool_call"


def test_mcp_approval_triplet_stability_guard_across_request_and_execution() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _McpRuntimeStub()
    expected_triplet = (True, "mcp_tool_call", "mcp.server:atlas")
    requested = runtime.request_gateway_action(
        action_type="mcp.tool.call",
        connector_key="mcp:atlas",
        plugin_name="mcp_runtime",
        request_payload={
            "action": "mcp.tool.call",
            "projected_name": "mcp__atlas__search_docs",
            "arguments": {"query": "triplet_stability_guard"},
            "tool_contract": {
                "name": "mcp__atlas__search_docs",
                "source": "mcp",
                "tool_family": "mcp_remote",
                "approval_required": expected_triplet[0],
                "approval_family": expected_triplet[1],
                "approval_scope": expected_triplet[2],
                "requires_confirmation": True,
                "mutates_ui": False,
            },
        },
        requested_by="runtime.mcp",
        trace_id="trace_mcp_approval_triplet_stability_guard",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="mcp approval required",
    )

    result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
        runtime,
        requested["approval_ticket"].approval_id,
        outcome="approved",
        decided_by="tester",
    )
    action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
    assert len(action_execute) == 1
    details = action_execute[0].details
    request_contract = requested["action_request"].payload["tool_contract"]
    execution_contract = details["execution_contract"]
    runtime_approval = details["mcp_execution"]["approval"]

    request_triplet = (
        bool(request_contract["approval_required"]),
        str(request_contract["approval_family"]),
        str(request_contract["approval_scope"]),
    )
    runtime_triplet = (
        bool(runtime_approval["required"]),
        str(runtime_approval["family"]),
        str(runtime_approval["scope"]),
    )
    assert request_triplet == expected_triplet
    assert runtime_triplet == expected_triplet
    assert execution_contract["approval_required"] is expected_triplet[0]
    assert runtime_triplet[2] == f"mcp.server:{execution_contract['connector_key'].split(':', 1)[1]}"
    assert isinstance(request_contract["approval_required"], bool)
    assert isinstance(runtime_approval["required"], bool)


def test_mcp_approval_triplet_variant_guard_changes_scope_only_by_server() -> None:
    class _DerivedScopeMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _DerivedScopeMcpRuntimeStub()

    servers = ["atlas", "atlas_prod", "team42"]
    required_values: set[bool] = set()
    family_values: set[str] = set()
    scope_values: set[str] = set()
    for server_name in servers:
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=f"mcp:{server_name}",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"triplet-variant-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_required": True,
                    "approval_family": "mcp_tool_call",
                    "approval_scope": f"mcp.server:{server_name}",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_approval_triplet_variant_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )

        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        request_contract = requested["action_request"].payload["tool_contract"]
        runtime_approval = details["mcp_execution"]["approval"]
        request_triplet = (
            bool(request_contract["approval_required"]),
            str(request_contract["approval_family"]),
            str(request_contract["approval_scope"]),
        )
        runtime_triplet = (
            bool(runtime_approval["required"]),
            str(runtime_approval["family"]),
            str(runtime_approval["scope"]),
        )
        assert request_triplet == runtime_triplet, server_name
        assert runtime_triplet[2] == f"mcp.server:{server_name}", server_name
        required_values.add(runtime_triplet[0])
        family_values.add(runtime_triplet[1])
        scope_values.add(runtime_triplet[2])

    assert required_values == {True}
    assert family_values == {"mcp_tool_call"}
    assert scope_values == {"mcp.server:atlas", "mcp.server:atlas_prod", "mcp.server:team42"}


def test_mcp_triplet_pairing_guard_binds_connector_scope_and_server_pairings() -> None:
    class _DerivedScopeMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _DerivedScopeMcpRuntimeStub()

    pairings: set[tuple[str, str]] = set()
    for server_name in ("atlas", "atlas_prod", "team42"):
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=f"mcp:{server_name}",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"triplet-pair-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_required": True,
                    "approval_family": "mcp_tool_call",
                    "approval_scope": f"mcp.server:{server_name}",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_triplet_pairing_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )

        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        connector_key = str(details["execution_contract"]["connector_key"] or "")
        scope = str(details["mcp_execution"]["approval"]["scope"] or "")
        runtime_server = str(details["mcp_execution"]["server_name"] or "")

        assert connector_key == f"mcp:{server_name}", server_name
        assert scope == f"mcp.server:{server_name}", server_name
        assert runtime_server == server_name, server_name
        assert details["mcp_execution"]["approval"]["required"] is True, server_name
        assert details["mcp_execution"]["approval"]["family"] == "mcp_tool_call", server_name
        pairings.add((connector_key, scope))

    assert pairings == {
        ("mcp:atlas", "mcp.server:atlas"),
        ("mcp:atlas_prod", "mcp.server:atlas_prod"),
        ("mcp:team42", "mcp.server:team42"),
    }


def test_mcp_connector_scope_family_matrix_guard_execution_nodes() -> None:
    class _DerivedScopeMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _DerivedScopeMcpRuntimeStub()

    matrix_rows: set[tuple[str, str, str]] = set()
    for server_name in ("atlas", "atlas_prod", "team42"):
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=f"mcp:{server_name}",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"matrix-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_required": True,
                    "approval_family": "mcp_tool_call",
                    "approval_scope": f"mcp.server:{server_name}",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_connector_scope_family_matrix_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        connector = str(details["execution_contract"]["connector_key"] or "")
        scope = str(details["mcp_execution"]["approval"]["scope"] or "")
        family = str(details["mcp_execution"]["approval"]["family"] or "")
        assert connector == f"mcp:{server_name}", server_name
        assert scope == f"mcp.server:{server_name}", server_name
        assert family == "mcp_tool_call", server_name
        assert details["execution_contract"]["tool_family"] == "mcp_tool_call", server_name
        matrix_rows.add((connector, scope, family))

    assert matrix_rows == {
        ("mcp:atlas", "mcp.server:atlas", "mcp_tool_call"),
        ("mcp:atlas_prod", "mcp.server:atlas_prod", "mcp_tool_call"),
        ("mcp:team42", "mcp.server:team42", "mcp_tool_call"),
    }


def test_mcp_matrix_field_type_guard_execution_nodes() -> None:
    class _DerivedScopeMcpRuntimeStub:
        @staticmethod
        def call_projected_tool(
            *, projected_name: str, arguments: dict[str, object] | None = None
        ) -> dict[str, object]:
            token = str(projected_name or "")
            parts = token.split("__")
            server_name = parts[1] if len(parts) >= 3 else "atlas"
            return {
                "ok": True,
                "projected_name": token,
                "server_name": server_name,
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": "mcp-ok"}]},
                "approval": {
                    "required": True,
                    "family": "mcp_tool_call",
                    "scope": f"mcp.server:{server_name}",
                },
            }

    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    runtime._mcp_runtime = _DerivedScopeMcpRuntimeStub()

    for server_name in ("atlas", "atlas_prod", "team42"):
        requested = runtime.request_gateway_action(
            action_type="mcp.tool.call",
            connector_key=f"mcp:{server_name}",
            plugin_name="mcp_runtime",
            request_payload={
                "action": "mcp.tool.call",
                "projected_name": f"mcp__{server_name}__search_docs",
                "arguments": {"query": f"type-matrix-{server_name}"},
                "tool_contract": {
                    "name": f"mcp__{server_name}__search_docs",
                    "approval_required": True,
                    "approval_family": "mcp_tool_call",
                    "approval_scope": f"mcp.server:{server_name}",
                },
            },
            requested_by="runtime.mcp",
            trace_id=f"trace_mcp_matrix_field_type_{server_name}",
            approval_required=True,
            approval_summary="Approve MCP tool call",
            approval_reason="mcp approval required",
        )
        result = approval_resolution_runtime.decide_gateway_approval_with_outcome(
            runtime,
            requested["approval_ticket"].approval_id,
            outcome="approved",
            decided_by="tester",
        )
        action_execute = [item for item in result["audit_records"] if item.stage == "action_execute"]
        assert len(action_execute) == 1, server_name
        details = action_execute[0].details
        connector_key = details["execution_contract"]["connector_key"]
        required = details["mcp_execution"]["approval"]["required"]
        family = details["mcp_execution"]["approval"]["family"]
        scope = details["mcp_execution"]["approval"]["scope"]

        assert isinstance(connector_key, str), server_name
        assert isinstance(required, bool), server_name
        assert isinstance(family, str), server_name
        assert isinstance(scope, str), server_name
