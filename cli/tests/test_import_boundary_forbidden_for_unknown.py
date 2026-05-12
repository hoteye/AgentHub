from __future__ import annotations

from cli.scripts import import_boundary_guard


def test_forbidden_for_returns_empty_tuple_for_unknown_module() -> None:
    unknown_module = "cli.agent_cli.unmapped.feature_entry"

    forbidden = import_boundary_guard.forbidden_for(unknown_module)

    assert forbidden == ()
