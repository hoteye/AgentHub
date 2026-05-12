from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.gateway_server.request_scope import gateway_request_scope, with_gateway_request_scope
from cli.agent_cli.runtime import AgentCliRuntime

class _Agent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_label": "test-provider",
            "platform_family": "linux",
            "platform_os": "linux",
            "shell_kind": "bash",
        }

def _runtime() -> AgentCliRuntime:
    runtime = AgentCliRuntime(agent=_Agent())
    runtime.tools._plugin_manager = SimpleNamespace()
    return runtime

def test_runtime_broadcasts_action_approval_and_audit_events() -> None:
    runtime = _runtime()
    scope = gateway_request_scope(
        request_id="req-broadcast-1",
        method="approvals.resolve",
        ingress_kind="gateway_dispatcher",
        actor_id="operator-1",
        trace_id="trace-broadcast-1",
    )

    def _run():
        return runtime.request_gateway_action(
            action_type="github.issues.create",
            connector_key="github_phase1",
            plugin_name="github_phase1",
            request_payload={"title": "Test"},
            requested_by="tester",
            trace_id="trace-broadcast-1",
            approval_required=True,
            approval_summary="Approve issue create",
        )

    with_gateway_request_scope(scope, _run)
    payload = runtime.gateway_broadcast_since(0)

    streams = [item["stream"] for item in payload["events"]]
    assert "workflow_runs" in streams
    assert "approvals" in streams
    assert "audit" in streams
    assert any(item["request_id"] == "req-broadcast-1" for item in payload["events"])

def test_runtime_broadcast_subscription_filters_by_stream() -> None:
    runtime = _runtime()
    received: list[dict[str, object]] = []
    runtime.subscribe_gateway_broadcast(
        subscription_id="sub-approvals",
        streams=["approvals"],
        callback=lambda frame: received.append(frame.to_dict()),
    )

    runtime.gateway_broadcaster.publish(stream="gateway_events", event="gateway.event.created", payload={"event_id": "e1"})
    runtime.gateway_broadcaster.publish(stream="approvals", event="approval.updated", payload={"approval_id": "a1"})

    assert received == [
        {
            "type": "event",
            "cursor": 2,
            "stream": "approvals",
            "event": "approval.updated",
            "payload": {"approval_id": "a1"},
            "created_at": received[0]["created_at"],
            "request_id": None,
            "trace_id": None,
            "correlation_id": None,
            "actor_id": None,
            "ingress_kind": None,
            "method": None,
            "plugin_id": None,
        }
    ]
