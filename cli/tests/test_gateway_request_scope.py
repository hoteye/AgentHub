from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.gateway_api.gui_bridge_api import dispatch_gui_bridge_action
from cli.agent_cli.gateway_server.dispatcher import GatewayDispatchResult, dispatch_gateway_method
from cli.agent_cli.gateway_server.request_scope import (
    gateway_request_scope,
    get_gateway_request_scope,
    with_gateway_plugin_scope,
    with_gateway_request_scope,
)

def test_gateway_request_scope_context_and_plugin_overlay() -> None:
    scope = gateway_request_scope(
        request_id="req-1",
        method="health.get",
        ingress_kind="gateway_dispatcher",
        actor_id="operator-1",
        trace_id="trace-1",
    )

    def _run() -> dict[str, str | None]:
        current = get_gateway_request_scope()
        assert current is not None

        def _with_plugin() -> dict[str, str | None]:
            scoped = get_gateway_request_scope()
            assert scoped is not None
            return {
                "request_id": scoped.request_id,
                "plugin_id": scoped.plugin_id,
            }

        return with_gateway_plugin_scope("psbc_policy", _with_plugin)

    result = with_gateway_request_scope(scope, _run)
    assert result == {"request_id": "req-1", "plugin_id": "psbc_policy"}

class _Runtime:
    agent = SimpleNamespace(
        provider_status=lambda: {
            "provider_label": "test",
            "platform_family": "linux",
            "platform_os": "linux",
            "shell_kind": "bash",
        }
    )

def test_dispatcher_exposes_request_scope_to_handlers() -> None:
    def _handler(**kwargs):
        scope = get_gateway_request_scope()
        assert scope is not None
        return GatewayDispatchResult(ok=True, result={"scope": scope.to_dict()})

    with patch.dict(
        "cli.agent_cli.gateway_server.dispatcher._DIRECT_METHOD_HANDLERS",
        {"health.get": _handler},
        clear=False,
    ):
        result = dispatch_gateway_method(
            method="health.get",
            params={},
            runtime=_Runtime(),
            request_id="req-health",
            client_info={"role": "operator", "actorId": "operator-1", "connId": "conn-7"},
        )

    assert result.ok is True
    assert result.result["scope"]["request_id"] == "req-health"
    assert result.result["scope"]["method"] == "health.get"
    assert result.result["scope"]["actor_id"] == "operator-1"
    assert result.result["scope"]["conn_id"] == "conn-7"

class _GuiRuntime:
    def __init__(self) -> None:
        self.scope_seen = None
        self.agent = SimpleNamespace(provider_status=lambda: {"provider_model": "gpt-5.4", "provider_label": "test"})
        self.tools = SimpleNamespace(_plugin_manager=None)

    def runtime_policy_status(self) -> dict[str, str]:
        self.scope_seen = get_gateway_request_scope()
        return {"approval_policy": "never", "sandbox_mode": "workspace-write"}

def test_gui_bridge_dispatch_runs_inside_gateway_request_scope() -> None:
    runtime = _GuiRuntime()

    result = dispatch_gui_bridge_action(
        runtime,
        action="settings.get",
        payload={},
        request_id="req-gui-1",
    )

    assert result["ok"] is True
    assert runtime.scope_seen is not None
    assert runtime.scope_seen.request_id == "req-gui-1"
    assert runtime.scope_seen.ingress_kind == "gui_bridge"
