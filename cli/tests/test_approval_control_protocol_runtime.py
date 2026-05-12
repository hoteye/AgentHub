from __future__ import annotations

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli import approval_control_protocol_runtime as protocol
from cli.agent_cli.models import ToolEvent


def test_shell_approval_projects_claude_can_use_tool_request() -> None:
    event = ToolEvent(
        name="shell_approval_requested",
        ok=True,
        summary="shell approval requested approval_1",
        payload={
            "approval_id": "approval_1",
            "command": "printf hello > out.txt",
            "reason": "needs workspace write",
            "provider_call_id": "call_1",
        },
    )

    request = protocol.control_request_for_tool_event(event)

    assert request == {
        "type": "control_request",
        "request_id": "approval_1",
        "request": {
            "subtype": "can_use_tool",
            "tool_name": "Bash",
            "input": {"command": "printf hello > out.txt"},
            "tool_use_id": "call_1",
            "decision_reason": "needs workspace write",
            "description": "shell approval requested approval_1",
        },
    }


def test_structured_write_approval_projects_native_write_tool_contract() -> None:
    event = ToolEvent(
        name="patch_approval_requested",
        ok=True,
        summary="patch approval requested approval_2",
        payload={
            "approval_id": "approval_2",
            "request_kind": "structured_write",
            "source_tool_name": "Write",
            "function_call_arguments": {
                "file_path": "hello.py",
                "content": "print('hello')\n",
            },
        },
    )

    request = protocol.control_request_for_tool_event(event)

    assert request is not None
    assert request["request_id"] == "approval_2"
    assert request["request"]["tool_name"] == "Write"
    assert request["request"]["input"] == {
        "file_path": "hello.py",
        "content": "print('hello')\n",
    }
    assert request["request"]["tool_use_id"] == "approval_2"


def test_control_response_maps_claude_allow_deny_and_internal_exact_decision() -> None:
    allow = {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "approval_1",
            "response": {"behavior": "allow", "updatedInput": {}},
        },
    }
    deny = {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "approval_2",
            "response": {"behavior": "deny", "message": "no"},
        },
    }
    rule = protocol.control_response_for_decision(
        approval_id="approval_3",
        decision=approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
    )

    assert protocol.approval_decision_from_control_response(allow)["decision"] == "accept"
    assert protocol.approval_decision_from_control_response(deny)["decision"] == "decline"
    assert (
        protocol.approval_decision_from_control_response(rule)["decision"]
        == "accept_with_execpolicy_amendment"
    )
