from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.web_tools_pure_helpers_runtime import (
    WebSearchExecutionContext,
    web_fetch_event_status_and_summary,
    web_fetch_result_arguments,
    web_search_event_status_and_summary,
    web_search_result_arguments,
)
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import _inject_route_metadata_into_result


def build_web_search_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    ok, summary = web_search_event_status_and_summary(payload)
    return event_factory("web_search", ok, summary, payload)


def annotate_structured_web_search_result(
    structured: CommandExecutionResult | None,
    *,
    context: WebSearchExecutionContext,
) -> CommandExecutionResult | None:
    if structured is None:
        return None
    return _inject_route_metadata_into_result(
        structured,
        **context.annotation_kwargs(),
    )


def build_web_search_result_from_event(
    *,
    query: str,
    limit: int,
    domains: list[str] | None,
    recency_days: int | None,
    market: str | None,
    result_from_event: Callable[..., CommandExecutionResult],
    web_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return result_from_event(
        "Search the web.",
        web_search_call(
            query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        ),
        tool_name="web_search",
        arguments=web_search_result_arguments(
            query=query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        ),
    )


def build_web_fetch_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    ok, summary = web_fetch_event_status_and_summary(payload)
    return event_factory("web_fetch", ok, summary, payload)


def build_web_fetch_result(
    *,
    url: str,
    max_chars: int,
    structured: CommandExecutionResult | None,
    result_from_event: Callable[..., CommandExecutionResult],
    web_fetch_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    if structured is not None:
        return structured
    return result_from_event(
        "Fetch the webpage.",
        web_fetch_call(url, max_chars=max_chars),
        tool_name="web_fetch",
        arguments=web_fetch_result_arguments(url=url, max_chars=max_chars),
    )


__all__ = [
    "annotate_structured_web_search_result",
    "build_web_fetch_event",
    "build_web_fetch_result",
    "build_web_search_event",
    "build_web_search_result_from_event",
]
