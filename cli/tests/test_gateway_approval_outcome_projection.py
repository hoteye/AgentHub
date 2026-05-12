from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cli.agent_cli.runtime_services import approval_resolution_gateway_runtime
from workers.actions import ActionResult


@dataclass
class _ApprovalTicket:
    approval_id: str
    trace_id: str
    status: str
    decision_note: str
    decision_at: str
    evidence_refs: tuple[str, ...] = ()


@dataclass
class _ActionRequest:
    action_id: str
    action_type: str
    action_family: str
    connector_key: str
    plugin_name: str
    payload: dict[str, Any]
    workflow_run_id: str | None = None


class _ActionWorker:
    @staticmethod
    def execute(request_payload: dict[str, Any]) -> ActionResult:
        return ActionResult(
            ok=True,
            action=str(request_payload.get("action") or "demo.noop"),
            summary="gateway action executed",
            output={"ok": True},
        )


class _Runtime:
    def __init__(self) -> None:
        self.action_worker = _ActionWorker()
        self.saved_tickets: list[_ApprovalTicket] = []

    def save_gateway_approval_ticket(self, ticket: _ApprovalTicket) -> None:
        self.saved_tickets.append(ticket)


def _gateway_action_request() -> _ActionRequest:
    return _ActionRequest(
        action_id="action_1",
        action_type="demo.noop",
        action_family="gateway",
        connector_key="demo_gateway",
        plugin_name="demo_plugin",
        payload={"action": "demo.noop", "parameters": {"x": 1}},
    )


@pytest.mark.parametrize(
    ("decision_note", "expected_outcome"),
    [
        ("approval rejected", "rejected"),
        ("approval timeout", "timed_out"),
        ("approval expired", "expired"),
    ],
)
def test_gateway_execution_details_project_decision_outcome_for_non_approved_paths(
    decision_note: str,
    expected_outcome: str,
) -> None:
    runtime = _Runtime()
    ticket = _ApprovalTicket(
        approval_id="approval_1",
        trace_id="trace_1",
        status="rejected",
        decision_note=decision_note,
        decision_at="2026-04-10T00:00:00+00:00",
    )

    result = approval_resolution_gateway_runtime.execute_approved_gateway_action(
        runtime,
        _gateway_action_request(),
        ticket,
    )

    details = dict(result["execution_details"] or {})
    contract = dict(details.get("execution_contract") or {})

    assert details["decision_outcome"] == expected_outcome
    assert contract["decision_outcome"] == expected_outcome
    assert contract["source"] == "gateway"
    assert contract["tool_family"] == "gateway_action"
