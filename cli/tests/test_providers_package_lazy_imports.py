from __future__ import annotations

import importlib
import sys


def _reset_provider_modules() -> None:
    for name in (
        "cli.agent_cli.core",
        "cli.agent_cli.providers",
        "cli.agent_cli.providers.interaction_contract_runtime",
        "cli.agent_cli.providers.chat_completions_planner",
        "cli.agent_cli.providers.anthropic_claude",
        "cli.agent_cli.providers.anthropic_claude_helpers",
        "cli.agent_cli.providers.openai_planner",
        "cli.agent_cli.core.turn_engine",
        "cli.agent_cli.core.provider_session",
    ):
        sys.modules.pop(name, None)


def _reset_runtime_core_modules() -> None:
    for name in (
        "cli.agent_cli.runtime_core",
        "cli.agent_cli.runtime_core.command_dispatch",
        "cli.agent_cli.runtime_core.command_parsing",
        "cli.agent_cli.runtime_core.tool_call_context_runtime",
        "cli.agent_cli.runtime_core.command_handlers",
        "cli.agent_cli.orchestration",
        "cli.agent_cli.orchestration.taskbook_dispatch",
    ):
        sys.modules.pop(name, None)


def test_interaction_contract_runtime_import_does_not_eagerly_load_planners() -> None:
    _reset_provider_modules()

    runtime = importlib.import_module("cli.agent_cli.providers.interaction_contract_runtime")

    assert runtime.__name__ == "cli.agent_cli.providers.interaction_contract_runtime"
    assert "cli.agent_cli.providers.chat_completions_planner" not in sys.modules
    assert "cli.agent_cli.providers.openai_planner" not in sys.modules
    assert "cli.agent_cli.core.turn_engine" not in sys.modules
    assert "cli.agent_cli.core.provider_session" not in sys.modules


def test_package_root_planner_exports_remain_available_via_lazy_lookup() -> None:
    _reset_provider_modules()

    providers = importlib.import_module("cli.agent_cli.providers")
    exported = providers.ChatCompletionsPlanner
    direct = importlib.import_module("cli.agent_cli.providers.chat_completions_planner").ChatCompletionsPlanner

    assert exported is direct


def test_package_root_lazy_export_map_is_fully_importable() -> None:
    _reset_provider_modules()

    providers = importlib.import_module("cli.agent_cli.providers")

    for export_name, (module_name, attribute_name) in providers._LAZY_EXPORTS.items():
        exported = getattr(providers, export_name)
        direct = getattr(importlib.import_module(module_name, providers.__name__), attribute_name)
        assert exported is direct, export_name


def test_core_package_root_does_not_eagerly_load_turn_engine_for_provider_session_exports() -> None:
    _reset_provider_modules()

    core = importlib.import_module("cli.agent_cli.core")

    provider_session = importlib.import_module("cli.agent_cli.core.provider_session")
    assert core.ProviderSessionResult is provider_session.ProviderSessionResult
    assert "cli.agent_cli.core.turn_engine" not in sys.modules


def test_runtime_core_package_root_keeps_exports_lazy_until_requested() -> None:
    _reset_runtime_core_modules()

    runtime_core = importlib.import_module("cli.agent_cli.runtime_core")

    assert "cli.agent_cli.runtime_core.command_dispatch" not in sys.modules
    assert "cli.agent_cli.runtime_core.command_parsing" not in sys.modules

    exported = runtime_core.parse_args
    direct = importlib.import_module("cli.agent_cli.runtime_core.command_parsing").parse_args

    assert exported is direct
    assert "cli.agent_cli.runtime_core.command_dispatch" not in sys.modules


def test_turn_engine_import_does_not_eagerly_load_runtime_command_dispatch_chain() -> None:
    _reset_provider_modules()
    _reset_runtime_core_modules()

    module = importlib.import_module("cli.agent_cli.core.turn_engine")

    assert module.TurnEngine.__name__ == "TurnEngine"
    assert "cli.agent_cli.runtime_core.command_dispatch" not in sys.modules
    assert "cli.agent_cli.orchestration.taskbook_dispatch" not in sys.modules
    assert "cli.agent_cli.providers.anthropic_claude_helpers" not in sys.modules
