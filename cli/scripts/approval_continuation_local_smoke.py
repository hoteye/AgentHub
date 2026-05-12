#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.agent_cli.gateway_core import InMemoryGatewayStateStore, create_action_request, create_approval_ticket
from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.runtime_core.command_dispatch import run_command_text_result
from cli.agent_cli.runtime_services import approval_continuation_runtime


@dataclass(frozen=True)
class SmokeCase:
    name: str
    tool_name: str
    decision: str
    provider_tool_type: str
    provider_raw_item: dict[str, Any]
    function_call_arguments: dict[str, Any]
    action_payload: dict[str, Any]
    approved_output: dict[str, Any]


SMOKE_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        name="approve_exec_command",
        tool_name="exec_command",
        decision="approve",
        provider_tool_type="local_shell_call",
        provider_raw_item={"type": "local_shell_call", "action": {"command": "echo approval-smoke"}},
        function_call_arguments={"cmd": "echo approval-smoke"},
        action_payload={"command": "echo approval-smoke"},
        approved_output={"stdout": "approval-smoke\n", "stderr": "", "exit_code": 0},
    ),
    SmokeCase(
        name="reject_exec_command",
        tool_name="exec_command",
        decision="reject",
        provider_tool_type="local_shell_call",
        provider_raw_item={"type": "local_shell_call", "action": {"command": "echo approval-smoke"}},
        function_call_arguments={"cmd": "echo approval-smoke"},
        action_payload={"command": "echo approval-smoke"},
        approved_output={"stdout": "approval-smoke\n", "stderr": "", "exit_code": 0},
    ),
    SmokeCase(
        name="approve_apply_patch",
        tool_name="apply_patch",
        decision="approve",
        provider_tool_type="function_call",
        provider_raw_item={"type": "function_call", "name": "apply_patch"},
        function_call_arguments={"patch": "*** Begin Patch\n*** Add File: smoke.txt\n+approval-smoke\n*** End Patch"},
        action_payload={"patch_text": "*** Begin Patch\n*** Add File: smoke.txt\n+approval-smoke\n*** End Patch"},
        approved_output={
            "function_call_output": (
                "Success. Updated the following files:\n"
                "A smoke.txt"
            ),
            "file_count": 1,
        },
    ),
    SmokeCase(
        name="reject_apply_patch",
        tool_name="apply_patch",
        decision="reject",
        provider_tool_type="function_call",
        provider_raw_item={"type": "function_call", "name": "apply_patch"},
        function_call_arguments={"patch": "*** Begin Patch\n*** Add File: smoke.txt\n+approval-smoke\n*** End Patch"},
        action_payload={"patch_text": "*** Begin Patch\n*** Add File: smoke.txt\n+approval-smoke\n*** End Patch"},
        approved_output={
            "function_call_output": (
                "Success. Updated the following files:\n"
                "A smoke.txt"
            ),
            "file_count": 1,
        },
    ),
)


@dataclass
class SmokeRuntime:
    gateway_state_store: InMemoryGatewayStateStore

    def __post_init__(self) -> None:
        self.history: list[dict[str, str]] = []
        self.thread_id = "approval_continuation_smoke"
        self._structured_tool_executor = object()
        self.agent = self
        self.plan_calls: list[dict[str, Any]] = []
        self.decide_calls = 0

    @staticmethod
    def _parse_args(arg_text: str):
        from cli.agent_cli.runtime_core import parse_args

        return parse_args(arg_text)

    @staticmethod
    def _is_interrupt_requested() -> bool:
        return False

    @staticmethod
    def _interrupt_tuple() -> tuple[str, list[ToolEvent]]:
        return "interrupted", []

    def save_gateway_action_request(self, item: Any) -> Any:
        return self.gateway_state_store.save_action_request(item)

    def save_gateway_approval_ticket(self, item: Any) -> Any:
        return self.gateway_state_store.save_approval_ticket(item)

    def decide_approval(self, approval_id: str, *, decision: Any, decided_by: str, decision_note: str = ""):
        self.decide_calls += 1
        ticket = self.gateway_state_store.get_approval_ticket(approval_id)
        if ticket is None:
            raise ValueError(f"unknown approval_id: {approval_id}")
        if str(ticket.status or "").strip().lower() != "pending":
            raise ValueError(f"approval already decided: {ticket.approval_id}")
        action = self.gateway_state_store.get_action_request(ticket.action_id)
        if action is None:
            raise ValueError(f"missing action for approval_id: {approval_id}")
        normalized_decision = str(decision or "").strip()
        approved = normalized_decision != "decline"
        ticket.status = "approved" if approved else "rejected"
        ticket.decision_by = decided_by
        ticket.decision_note = decision_note
        ticket.decision_type = normalized_decision
        self.save_gateway_approval_ticket(ticket)
        action_result = _action_result_for_decision(action, approved=approved)
        response = {
            "approval_ticket": ticket,
            "action_request": action,
            "action_result": action_result,
            "tool_events": [
                ToolEvent(
                    name="approval_decision",
                    ok=True,
                    summary=f"{ticket.status} {approval_id}",
                    payload={
                        "approval_id": approval_id,
                        "status": ticket.status,
                        "action_type": action.action_type,
                    },
                )
            ],
            "item_events": [],
            "turn_events": [],
        }
        response["continuation"] = approval_continuation_runtime.prepare_resume_after_approval(
            self,
            approval_id=approval_id,
            decision_response=response,
        )
        return response

    def plan(self, user_text: str, history: list[dict[str, str]], **kwargs: Any) -> AgentIntent:
        del history
        self.plan_calls.append({"user_text": user_text, **kwargs})
        return AgentIntent(assistant_text="continued after approval smoke")


def _action_result_for_decision(action: Any, *, approved: bool) -> dict[str, Any] | None:
    if not approved:
        return None
    metadata = dict(getattr(action, "metadata", {}) or {})
    output = dict(metadata.get("smoke_approved_output") or {})
    if str(getattr(action, "action_type", "") or "") == "apply_patch":
        return {
            "ok": True,
            "action": "apply_patch",
            "summary": "patch completed",
            "output": output,
        }
    return {
        "ok": True,
        "action": "shell_command_start",
        "summary": "shell completed",
        "output": output,
    }


def _continuation_record(case: SmokeCase) -> dict[str, Any]:
    call_id = f"call_smoke_{case.name}"
    return {
        "schema_version": 1,
        "approval_id": "pending",
        "action_id": "pending",
        "provider_session_kind": "codex_openai",
        "previous_response_id": f"resp_{case.name}",
        "provider_call_id": call_id,
        "function_call_name": case.tool_name,
        "function_call_arguments": dict(case.function_call_arguments),
        "provider_tool_type": case.provider_tool_type,
        "provider_raw_item": dict(case.provider_raw_item),
        "continuation_input_items": [
            {
                "type": case.provider_tool_type,
                "call_id": call_id,
                "name": case.tool_name,
            }
        ],
        "replay_input_items": [{"role": "user", "content": f"run {case.name} smoke"}],
        "status": "pending",
    }


def _create_pending(store: InMemoryGatewayStateStore, case: SmokeCase) -> str:
    metadata = {
        "pending_tool_continuation": _continuation_record(case),
        "smoke_approved_output": dict(case.approved_output),
    }
    action = create_action_request(
        action_type="apply_patch" if case.tool_name == "apply_patch" else "shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id=f"trace_{case.name}",
        requested_by="smoke",
        payload=dict(case.action_payload),
        metadata=metadata,
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="smoke", reason="smoke approval")
    action.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_action_request(action)
    ticket.metadata["pending_tool_continuation"] = dict(action.metadata["pending_tool_continuation"])
    store.save_approval_ticket(ticket)
    return ticket.approval_id


def _tool_output_call_ids(continuation: dict[str, Any]) -> list[str]:
    return [
        str(item.get("call_id") or "").strip()
        for item in list(continuation.get("tool_output_items") or [])
        if isinstance(item, dict)
    ]


def _run_case(case: SmokeCase) -> dict[str, Any]:
    store = InMemoryGatewayStateStore()
    approval_id = _create_pending(store, case)
    runtime = SmokeRuntime(store)
    result = run_command_text_result(runtime, f"/{case.decision} {approval_id}")
    plan_call = runtime.plan_calls[0] if runtime.plan_calls else {}
    continuation = dict((result.tool_events[0].payload or {}).get("continuation") or {}) if result.tool_events else {}
    expected_call_id = f"call_smoke_{case.name}"
    reasons: list[str] = []
    if runtime.decide_calls != 1:
        reasons.append("decision_not_called_once")
    if result.assistant_text != "continued after approval smoke":
        reasons.append("missing_resumed_assistant_text")
    if not runtime.plan_calls:
        reasons.append("planner_not_called")
    if continuation.get("continuation_status") != "completed":
        reasons.append("continuation_not_completed")
    if not bool(continuation.get("continuation_attempted")):
        reasons.append("continuation_not_attempted")
    if continuation.get("provider_call_id") != expected_call_id:
        reasons.append("provider_call_id_mismatch")
    if expected_call_id not in _tool_output_call_ids(continuation):
        reasons.append("tool_output_call_id_missing")
    if plan_call.get("initial_previous_response_id") != f"resp_{case.name}":
        reasons.append("previous_response_id_mismatch")
    input_items = [dict(item) for item in list(plan_call.get("input_items") or []) if isinstance(item, dict)]
    if not input_items:
        reasons.append("missing_resume_input_items")
    return {
        "case": case.name,
        "tool_name": case.tool_name,
        "decision": case.decision,
        "ok": not reasons,
        "reasons": reasons,
        "approval_id": approval_id,
        "assistant_text": result.assistant_text,
        "tool_event_names": [event.name for event in result.tool_events],
        "continuation": {
            "continuation_attempted": bool(continuation.get("continuation_attempted")),
            "continuation_status": str(continuation.get("continuation_status") or ""),
            "provider_call_id": str(continuation.get("provider_call_id") or ""),
            "function_call_name": str(continuation.get("function_call_name") or ""),
            "provider_tool_type": str(continuation.get("provider_tool_type") or ""),
            "tool_output_call_ids": _tool_output_call_ids(continuation),
        },
        "previous_response_id": plan_call.get("initial_previous_response_id"),
        "resume_input_types": [str(item.get("type") or item.get("role") or "") for item in input_items],
        "last_input_item": input_items[-1] if input_items else None,
    }


def _selected_cases(names: list[str]) -> list[SmokeCase]:
    if not names:
        return list(SMOKE_CASES)
    by_name = {case.name: case for case in SMOKE_CASES}
    selected: list[SmokeCase] = []
    for name in names:
        if name not in by_name:
            available = ", ".join(sorted(by_name))
            raise SystemExit(f"unknown case `{name}`; available: {available}")
        selected.append(by_name[name])
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local approval continuation smoke tests.")
    parser.add_argument("--case", action="append", default=[], help="Case name to run. Repeat to restrict.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cases = _selected_cases([str(item) for item in list(args.case or [])])
    results = [_run_case(case) for case in cases]
    report = {
        "ok": all(bool(item.get("ok")) for item in results),
        "case_count": len(results),
        "pass_count": sum(1 for item in results if item.get("ok")),
        "fail_count": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2 if args.json else None, sort_keys=not args.json)
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
