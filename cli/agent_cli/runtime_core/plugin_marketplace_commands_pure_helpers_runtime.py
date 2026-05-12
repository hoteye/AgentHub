from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.host.plugin_marketplace import PluginMarketplaceStore


def plugin_manager(runtime: Any) -> Any | None:
    tools = getattr(runtime, "tools", None)
    if tools is None:
        return None
    return getattr(tools, "_plugin_manager", None)


def marketplace_store(runtime: Any) -> PluginMarketplaceStore:
    manager = plugin_manager(runtime)
    reference_home = getattr(manager, "reference_home", None)
    if reference_home is None:
        reference_home = Path.home() / ".agent_cli"
    return PluginMarketplaceStore.from_reference_home(Path(reference_home))
