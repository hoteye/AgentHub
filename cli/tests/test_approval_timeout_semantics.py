from __future__ import annotations

from typing import Dict

from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_services import approval_resolution_runtime
from workers.actions import ActionResult


class _Agent:
    @staticmethod
    def provider_status() -> Dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "task-l",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(*args, **kwargs):
        raise AssertionError("planner should not run in timeout semantics tests")


class _ActionWorker:
    @staticmethod
    def execute(request):
        return ActionResult(
            ok=True,
            action=str(request.get("action") or ""),
            summary="fake action executed",
            output={"artifact_refs": []},
        )


def _request_mcp_gateway_action(runtime: AgentCliRuntime, label: str) -> Dict[str, object]:
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
        trace_id=f"trace_timeout_semantics_{label}",
        approval_required=True,
        approval_summary="Approve MCP tool call",
        approval_reason="timeout semantics guard",
    )


def test_timeout_decision_declares_rejected_status_with_stable_note() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = _request_mcp_gateway_action(runtime, label="timeout-default")

    result = approval_resolution_runtime.decide_gateway_approval_timeout(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_timeout",
    )

    assert result["decision_outcome"] == "timed_out"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_note == "approval timeout"


def test_timeout_decision_preserves_custom_note() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = _request_mcp_gateway_action(runtime, label="timeout-custom")

    custom_note = "timeout by watchdog"
    result = approval_resolution_runtime.decide_gateway_approval_timeout(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_timeout",
        decision_note=custom_note,
    )

    assert result["decision_outcome"] == "timed_out"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_note == custom_note


def test_expired_decision_declares_rejected_status_with_expired_note() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = _request_mcp_gateway_action(runtime, label="expired-default")

    result = approval_resolution_runtime.decide_gateway_approval_expired(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_gc",
    )

    assert result["decision_outcome"] == "expired"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_note == "approval expired"


def test_expired_decision_preserves_custom_note() -> None:
    runtime = AgentCliRuntime(agent=_Agent(), action_worker=_ActionWorker())
    requested = _request_mcp_gateway_action(runtime, label="expired-custom")

    custom_note = "expired by GC sweep"
    result = approval_resolution_runtime.decide_gateway_approval_expired(
        runtime,
        requested["approval_ticket"].approval_id,
        decided_by="system_gc",
        decision_note=custom_note,
    )

    assert result["decision_outcome"] == "expired"
    assert result["approval_ticket"].status == "rejected"
    assert result["approval_ticket"].decision_note == custom_note
