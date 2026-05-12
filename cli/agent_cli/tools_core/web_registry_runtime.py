from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.tools_core import browser_web_runtime


def get_web_search_tools(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
    project_root: Path,
) -> Any:
    if cached_tools is not None:
        return cached_tools
    web_search_tools_cls = getattr(load_project_tool_module("web_search_tools"), "WebSearchTools")
    policy_path = project_root / "config" / "web_tools.toml"
    return web_search_tools_cls(policy_path=str(policy_path))


def get_browser_client(registry: Any) -> Any | None:
    return browser_web_runtime.get_browser_client(registry)


def profile_prefers_local_browser(registry: Any, *, profile: str | None) -> bool:
    return browser_web_runtime.profile_prefers_local_browser(registry, profile=profile)


def get_browser_executor(
    registry: Any,
    *,
    profile: str | None = None,
    transport: str | None = None,
) -> Any | None:
    return browser_web_runtime.get_browser_executor(
        registry,
        profile=profile,
        transport=transport,
    )
