from __future__ import annotations

from typing import Any, List, Optional

from cli.agent_cli.tools_core import browser_web_runtime, tool_library_adapter_runtime, web_tools_runtime


def _web_search_provider_config_factory(registry: Any):
    resolver = getattr(registry, "_web_search_provider_config_factory", None)
    if callable(resolver):
        return resolver
    if hasattr(registry, "_web_search_provider_config"):
        return lambda: getattr(registry, "_web_search_provider_config", None)
    return None


def web_search(
    registry: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Any:
    return tool_library_adapter_runtime.call_web_search_tool(
        web_tools_runtime.web_search,
        registry,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        provider_config_factory=_web_search_provider_config_factory(registry),
    )


def web_search_result(
    registry: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Any:
    return tool_library_adapter_runtime.call_web_search_tool_result(
        web_tools_runtime.web_search_result,
        registry,
        fallback_arg="web_search_call",
        fallback_call=registry.web_search,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        provider_config_factory=_web_search_provider_config_factory(registry),
    )


def web_fetch(registry: Any, url: str, *, max_chars: int = 12000) -> Any:
    return browser_web_runtime.web_fetch(
        registry,
        url=url,
        max_chars=max_chars,
    )


def web_fetch_result(registry: Any, url: str, *, max_chars: int = 12000) -> Any:
    return browser_web_runtime.web_fetch_result(
        registry,
        url=url,
        max_chars=max_chars,
    )


__all__ = [
    "web_fetch",
    "web_fetch_result",
    "web_search",
    "web_search_result",
]
