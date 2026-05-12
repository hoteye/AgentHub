from __future__ import annotations

from cli.agent_cli.approval_continuation_projection_runtime import (
    camel_case_continuation_fields,
    continuation_fields,
    continuation_status_from_metadata,
)
from cli.agent_cli.models import ToolEvent


def test_continuation_fields_are_absent_without_continuation_payload() -> None:
    assert continuation_fields(tool_events=[]) == {}


def test_continuation_fields_project_completed_degraded_and_failed_statuses() -> None:
    statuses = ("completed", "degraded", "failed")

    for status in statuses:
        fields = continuation_fields(
            tool_events=[
                ToolEvent(
                    name="approval_decision",
                    ok=status != "failed",
                    summary=status,
                    payload={
                        "continuation": {
                            "continuation_attempted": True,
                            "continuation_status": status,
                            "approval_id": "approval_1",
                            "action_id": "action_1",
                            "provider_call_id": "call_1",
                            "function_call_name": "exec_command",
                            "provider_tool_type": "local_shell_call",
                        }
                    },
                )
            ]
        )

        assert fields["continuation_attempted"] is True
        assert fields["continuation_status"] == status
        assert fields["continuation"]["provider_call_id"] == "call_1"


def test_camel_case_continuation_fields_keep_rpc_contract_lightweight() -> None:
    fields = camel_case_continuation_fields(
        {
            "continuation": {
                "continuation_attempted": True,
                "continuation_status": "completed",
                "approval_id": "approval_1",
                "provider_call_id": "call_1",
            },
            "continuation_attempted": True,
            "continuation_status": "completed",
        }
    )

    assert fields == {
        "continuation": {
            "continuationAttempted": True,
            "continuationStatus": "completed",
            "approvalId": "approval_1",
            "providerCallId": "call_1",
        },
        "continuationAttempted": True,
        "continuationStatus": "completed",
    }


class _GatewayItem:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_continuation_status_from_metadata_projects_completed_result() -> None:
    ticket = _GatewayItem(
        approval_id="approval_1",
        action_id="action_1",
        status="approved",
        metadata={
            "approval_continuation_result": {
                "continuation_attempted": True,
                "continuation_status": "completed",
                "approval_id": "approval_1",
                "action_id": "action_1",
                "provider_call_id": "call_1",
                "function_call_name": "exec_command",
            }
        },
    )

    summary = continuation_status_from_metadata(ticket=ticket)

    assert summary["continuation_status"] == "completed"
    assert summary["continuation_stale"] is False
    assert summary["continuation_source"] == "result"
    assert summary["provider_call_id"] == "call_1"


def test_continuation_status_from_metadata_marks_decided_pending_context_stale() -> None:
    ticket = _GatewayItem(
        approval_id="approval_1",
        action_id="action_1",
        status="approved",
        metadata={
            "pending_tool_continuation": {
                "approval_id": "approval_1",
                "action_id": "action_1",
                "provider_call_id": "call_1",
                "function_call_name": "exec_command",
                "provider_tool_type": "local_shell_call",
            }
        },
    )

    summary = continuation_status_from_metadata(ticket=ticket)

    assert summary["continuation_status"] == "stale_pending"
    assert summary["continuation_stale"] is True
    assert summary["continuation_source"] == "pending"
