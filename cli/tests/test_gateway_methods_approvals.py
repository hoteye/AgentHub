from __future__ import annotations

from cli.agent_cli.gateway_server.methods.approvals import APPROVALS_FAMILY, approvals_handlers

def test_approvals_family_freezes_initial_method_names() -> None:
    assert APPROVALS_FAMILY.methods == (
        "approvals.list",
        "approvals.get",
        "approvals.resolve",
    )
    assert set(approvals_handlers) == set(APPROVALS_FAMILY.methods)

def test_approvals_stub_handler_is_registry_ready() -> None:
    result = approvals_handlers["approvals.resolve"](params={"approval_id": "approval_1"})

    assert result["family"] == "approvals"
    assert result["method"] == "approvals.resolve"
    assert result["params"]["approval_id"] == "approval_1"
