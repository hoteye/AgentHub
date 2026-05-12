from __future__ import annotations

from cli.agent_cli.gateway_server.methods.health import HEALTH_FAMILY, health_handlers

def test_health_family_freezes_initial_method_names() -> None:
    assert HEALTH_FAMILY.family_name == "health"
    assert HEALTH_FAMILY.methods == ("health.get", "health.probes")
    assert set(health_handlers) == {"health.get", "health.probes"}

def test_health_stub_handler_keeps_method_identity() -> None:
    result = health_handlers["health.get"]()

    assert result["family"] == "health"
    assert result["method"] == "health.get"
    assert "readiness summary" in result["summary"]
