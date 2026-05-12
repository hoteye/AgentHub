from __future__ import annotations

from cli.scripts import import_boundary_guard


def test_import_boundary_rules_keep_key_owner_to_forbidden_contract() -> None:
    rules = import_boundary_guard.RULES

    assert rules["cli.agent_cli.core."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.runtime_core."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.runtime_services."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.background_tasks."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.providers."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.tools_core."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.gateway_server."] == ("cli.agent_cli.ui",)
    assert rules["cli.agent_cli.ui."] == ("cli.agent_cli.runtime",)


def test_import_boundary_forbidden_for_resolves_by_owner_prefix() -> None:
    assert import_boundary_guard.forbidden_for("cli.agent_cli.runtime_core.command_dispatch") == (
        "cli.agent_cli.ui",
    )
    assert import_boundary_guard.forbidden_for("cli.agent_cli.background_tasks.adapter") == (
        "cli.agent_cli.ui",
    )
    assert import_boundary_guard.forbidden_for("cli.agent_cli.ui.status_controller") == (
        "cli.agent_cli.runtime",
    )
    assert import_boundary_guard.forbidden_for("cli.agent_cli.runtime") == ()
