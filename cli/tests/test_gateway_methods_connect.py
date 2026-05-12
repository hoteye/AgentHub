from __future__ import annotations

from cli.agent_cli.gateway_server.methods.connect import CONNECT_FAMILY, connect_handlers

def test_connect_family_exposes_registry_ready_handler_map() -> None:
    assert CONNECT_FAMILY.family_name == "connect"
    assert CONNECT_FAMILY.methods == (
        "connect.initialize",
        "connect.capabilities",
        "connect.ping",
    )
    assert set(connect_handlers) == set(CONNECT_FAMILY.methods)

def test_connect_stub_handler_returns_stable_placeholder_payload() -> None:
    result = connect_handlers["connect.initialize"](params={"client": "test"})

    assert result["ok"] is False
    assert result["status"] == "stub"
    assert result["family"] == "connect"
    assert result["method"] == "connect.initialize"
    assert result["params"] == {"client": "test"}
