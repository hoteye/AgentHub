from __future__ import annotations

import ast
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_module_name_converts_python_path_to_module_path() -> None:
    path = Path("cli/agent_cli/runtime_core/command_dispatch.py")
    assert import_boundary_guard.module_name(path) == "cli.agent_cli.runtime_core.command_dispatch"


def test_resolve_import_handles_absolute_and_relative_imports() -> None:
    current_module = "cli.agent_cli.runtime_core.command_dispatch"
    tree = ast.parse(
        "from cli.agent_cli.ui.status import render\n"
        "from ..ui import panel\n"
        "from ..runtime_services import helper\n"
        "from ....outside import thing\n"
    )
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

    resolved = [import_boundary_guard.resolve_import(current_module, node) for node in nodes]
    assert resolved == [
        "cli.agent_cli.ui.status",
        "cli.agent_cli.ui",
        "cli.agent_cli.runtime_services",
        "outside",
    ]


def test_is_forbidden_matches_exact_and_descendant_modules() -> None:
    forbidden = "cli.agent_cli.ui"
    assert import_boundary_guard.is_forbidden("cli.agent_cli.ui", forbidden) is True
    assert import_boundary_guard.is_forbidden("cli.agent_cli.ui.widgets", forbidden) is True
    assert import_boundary_guard.is_forbidden("cli.agent_cli.runtime", forbidden) is False
