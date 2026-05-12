from __future__ import annotations

from cli.agent_cli.gateway_api.gateway_ws import (
    GATEWAY_WS_STREAMS,
    gateway_ws_capabilities,
    gateway_ws_poll,
    gateway_ws_subscribe,
    gateway_ws_unsubscribe,
)
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

def test_gateway_ws_subscription_and_poll_filter_streams() -> None:
    runtime = AgentCliRuntime(agent=_Agent())
    subscription = gateway_ws_subscribe(runtime, subscription_id="sub-1", streams=["approvals"])
    runtime.gateway_broadcaster.publish(stream="gateway_events", event="gateway.event.created", payload={"event_id": "e1"})
    runtime.gateway_broadcaster.publish(stream="approvals", event="approval.updated", payload={"approval_id": "a1"})

    polled = gateway_ws_poll(runtime, cursor=0, streams=["approvals"])

    assert subscription.to_dict() == {"subscriptionId": "sub-1", "streams": ["approvals"]}
    assert [item["stream"] for item in polled["events"]] == ["approvals"]
    assert gateway_ws_unsubscribe(runtime, subscription_id="sub-1") is True

def test_gateway_ws_capabilities_expose_protocol_streams_commands_and_methods() -> None:
    capabilities = gateway_ws_capabilities()

    assert capabilities["protocolVersions"] == ["v1"]
    assert capabilities["streams"] == list(GATEWAY_WS_STREAMS)
    assert capabilities["commands"] == ["subscribe", "unsubscribe", "poll", "ping"]
    assert "connect.initialize" in capabilities["methods"]
    assert "github.webhook.ingest" in capabilities["methods"]

def test_gateway_ws_subscription_defaults_to_all_streams_and_dedupes_inputs() -> None:
    runtime = AgentCliRuntime(agent=_Agent())

    subscription = gateway_ws_subscribe(
        runtime,
        subscription_id="sub-all",
        streams=["approvals", "approvals", "", "audit"],
    )
    defaulted = gateway_ws_subscribe(runtime, subscription_id="sub-default")

    assert subscription.to_dict() == {"subscriptionId": "sub-all", "streams": ["approvals", "audit"]}
    assert defaulted.to_dict() == {
        "subscriptionId": "sub-default",
        "streams": list(GATEWAY_WS_STREAMS),
    }
