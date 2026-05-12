from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.tool_backend_registry import backend_spec_by_id
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_normalization_helpers_runtime import (
    execute_web_search_payload,
    normalize_web_search_payload,
    resolve_web_search_execution_context,
)
from cli.agent_cli.tools_core.web_tools_projection_helpers_runtime import (
    build_web_fetch_event,
    build_web_search_event,
)
from cli.agent_cli.tools_core.web_tools_result_runtime import (
    web_fetch_result as _web_fetch_result,
)
from cli.agent_cli.tools_core.web_tools_result_runtime import (
    web_search_result as _web_search_result,
)
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import (
    _native_web_search_payload,
    _openai_native_web_search_payload,
    _resolve_native_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import (
    runtime_web_search_route as _runtime_web_search_route,
)
from shared.document_tools.web_search_tools_support import _web_fetch_failure_payload


def runtime_web_search_route(
    *,
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[
        [WebSearchResolverInput], Any
    ] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[
        [Any], Any
    ] = _resolve_native_web_search_capability,
) -> dict[str, Any]:
    return _runtime_web_search_route(
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
    domains: list[str] | None = None,
    recency_days: int | None = None,
    market: str | None = None,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[
        [WebSearchResolverInput], Any
    ] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[
        [Any], Any
    ] = _resolve_native_web_search_capability,
    native_web_search_payload_fn: Callable[..., dict[str, Any]] = _native_web_search_payload,
    openai_native_web_search_payload_fn: Callable[
        ..., dict[str, Any]
    ] = _openai_native_web_search_payload,
) -> ToolEvent:
    context = resolve_web_search_execution_context(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )
    payload = execute_web_search_payload(
        context=context,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        web_search_tools_factory=web_search_tools_factory,
        native_web_search_payload_fn=native_web_search_payload_fn,
        openai_native_web_search_payload_fn=openai_native_web_search_payload_fn,
    )
    normalized_payload = normalize_web_search_payload(
        query=query,
        payload=payload,
        context=context,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
    )
    return build_web_search_event(
        payload=normalized_payload,
        event_factory=event_factory,
    )


def web_search_result(
    *,
    query: str,
    limit: int = 5,
    domains: list[str] | None = None,
    recency_days: int | None = None,
    market: str | None = None,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    web_search_call: Callable[..., ToolEvent],
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[
        [WebSearchResolverInput], Any
    ] = resolve_web_search_capability,
    resolve_native_web_search_capability_fn: Callable[
        [Any], Any
    ] = _resolve_native_web_search_capability,
) -> CommandExecutionResult:
    return _web_search_result(
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
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    try:
        payload = web_search_tools_factory().web_fetch(url, max_chars=max_chars)
    except Exception as exc:
        payload = {
            "ok": False,
            "url": str(url or "").strip(),
            "max_chars": max_chars,
            **_web_fetch_failure_payload(exc),
        }
    return build_web_fetch_event(
        payload=payload,
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
    return _web_fetch_result(
        url=url,
        max_chars=max_chars,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        web_fetch_call=web_fetch_call,
    )
