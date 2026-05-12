from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import web_tools_browser_facade_runtime, web_tools_search_runtime
from cli.agent_cli.tools_core.tool_backend_registry import (
    backend_spec_by_id,
)
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import (
    _native_web_search_payload,
    _openai_native_web_search_payload,
    _resolve_native_web_search_capability,
)


def runtime_web_search_route(
    *,
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[[Any], Any] = _resolve_native_web_search_capability,
) -> dict[str, Any]:
    return web_tools_search_runtime.runtime_web_search_route(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )


def web_search(
    *,
    query: str,
    limit: int = 5,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[[Any], Any] = _resolve_native_web_search_capability,
    native_web_search_payload_fn: Callable[..., Dict[str, Any]] = _native_web_search_payload,
    openai_native_web_search_payload_fn: Callable[..., Dict[str, Any]] = _openai_native_web_search_payload,
) -> ToolEvent:
    return web_tools_search_runtime.web_search(
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
        native_web_search_payload_fn=native_web_search_payload_fn,
        openai_native_web_search_payload_fn=openai_native_web_search_payload_fn,
    )


def web_search_result(
    *,
    query: str,
    limit: int = 5,
    domains: Optional[List[str]] = None,
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
    return web_tools_search_runtime.web_search_result(
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        web_search_call=web_search_call,
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )


def web_fetch(
    *,
    url: str,
    max_chars: int = 12000,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return web_tools_search_runtime.web_fetch(
        url=url,
        max_chars=max_chars,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
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
    return web_tools_search_runtime.web_fetch_result(
        url=url,
        max_chars=max_chars,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        web_fetch_call=web_fetch_call,
    )


def open(
    *,
    ref: str,
    line: int = 1,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return web_tools_browser_facade_runtime.open(
        ref=ref,
        line=line,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def open_result(
    *,
    ref: str,
    line: int = 1,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    open_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return web_tools_browser_facade_runtime.open_result(
        ref=ref,
        line=line,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        open_call=open_call,
    )


def click(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return web_tools_browser_facade_runtime.click(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def click_result(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    click_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return web_tools_browser_facade_runtime.click_result(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        click_call=click_call,
    )


def find(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return web_tools_browser_facade_runtime.find(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def find_result(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    find_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return web_tools_browser_facade_runtime.find_result(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        find_call=find_call,
    )
