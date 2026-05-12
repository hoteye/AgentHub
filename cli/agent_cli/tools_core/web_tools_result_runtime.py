from __future__ import annotations

from typing import Any, Callable, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.tool_backend_registry import BACKEND_LOCAL_WEB_SEARCH
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_projection_helpers_runtime import (
    annotate_structured_web_search_result,
    build_web_fetch_result,
    build_web_search_result_from_event,
)
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import (
    _resolve_native_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_normalization_helpers_runtime import (
    resolve_web_search_execution_context,
)


def web_search_result(
    *,
    query: str,
    limit: int = 5,
    domains: Optional[list[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    web_search_call: Callable[..., ToolEvent],
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    resolve_native_web_search_capability_fn: Callable[[Any], Any] = _resolve_native_web_search_capability,
) -> CommandExecutionResult:
    context = resolve_web_search_execution_context(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )
    if context.effective_backend_id == BACKEND_LOCAL_WEB_SEARCH:
        structured = call_structured_helper(
            web_search_tools_factory(),
            "web_search_result",
            query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        )
        annotated = annotate_structured_web_search_result(structured, context=context)
        if annotated is not None:
            return annotated
    return build_web_search_result_from_event(
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        result_from_event=result_from_event,
        web_search_call=web_search_call,
    )


def web_fetch_result(
    *,
    url: str,
    max_chars: int = 12000,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    web_fetch_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    structured = call_structured_helper(
        web_search_tools_factory(),
        "web_fetch_result",
        url,
        max_chars=max_chars,
    )
    return build_web_fetch_result(
        url=url,
        max_chars=max_chars,
        structured=structured,
        result_from_event=result_from_event,
        web_fetch_call=web_fetch_call,
    )


__all__ = ["web_fetch_result", "web_search_result"]
