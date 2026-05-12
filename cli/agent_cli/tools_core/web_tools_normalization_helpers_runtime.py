from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
    backend_spec_by_id,
)
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_output_runtime import (
    web_search_function_call_output as _web_search_function_call_output,
)
from cli.agent_cli.tools_core.web_tools_pure_helpers_runtime import WebSearchExecutionContext
from cli.agent_cli.tools_core.web_tools_route_helpers_runtime import (
    _annotate_web_search_payload,
    _effective_web_search_backend,
    _native_web_search_payload,
    _openai_native_web_search_payload,
    _resolve_native_web_search_capability,
    _resolve_web_search_route,
)


def resolve_web_search_execution_context(
    *,
    provider_config: Any | None = None,
    provider_config_factory: Callable[[], Any] | None = None,
    probe_cache_lookup: Callable[[Any], Any] | None = None,
    resolve_web_search_capability_fn: Callable[[WebSearchResolverInput], Any] = resolve_web_search_capability,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
    resolve_native_web_search_capability_fn: Callable[[Any], Any] = _resolve_native_web_search_capability,
) -> WebSearchExecutionContext:
    route, resolved_config = _resolve_web_search_route(
        provider_config=provider_config,
        provider_config_factory=provider_config_factory,
        probe_cache_lookup=probe_cache_lookup,
        resolve_web_search_capability_fn=resolve_web_search_capability_fn,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
    )
    effective_backend_id, execution_path, fallback_reason = _effective_web_search_backend(
        route,
        provider_config=resolved_config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )
    return WebSearchExecutionContext(
        route=route,
        resolved_config=resolved_config,
        effective_backend_id=effective_backend_id,
        execution_path=execution_path,
        fallback_reason=fallback_reason,
    )


def execute_web_search_payload(
    *,
    context: WebSearchExecutionContext,
    query: str,
    limit: int,
    domains: list[str] | None,
    recency_days: int | None,
    market: str | None,
    web_search_tools_factory: Callable[[], Any],
    native_web_search_payload_fn: Callable[..., dict[str, Any]] = _native_web_search_payload,
    openai_native_web_search_payload_fn: Callable[..., dict[str, Any]] = _openai_native_web_search_payload,
) -> dict[str, Any]:
    if (
        context.effective_backend_id == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
        and context.resolved_config is not None
    ):
        return native_web_search_payload_fn(
            context.resolved_config,
            query=query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        )
    if (
        context.effective_backend_id == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
        and context.resolved_config is not None
    ):
        return openai_native_web_search_payload_fn(
            context.resolved_config,
            query=query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        )
    return web_search_tools_factory().web_search(
        query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )


def normalize_web_search_payload(
    *,
    query: str,
    payload: dict[str, Any] | None,
    context: WebSearchExecutionContext,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
) -> dict[str, Any]:
    normalized_payload = _annotate_web_search_payload(
        dict(payload or {}),
        backend_spec_by_id_fn=backend_spec_by_id_fn,
        **context.annotation_kwargs(),
    )
    normalized_payload.setdefault("function_call_output", _web_search_function_call_output(query, normalized_payload))
    return normalized_payload


__all__ = [
    "execute_web_search_payload",
    "normalize_web_search_payload",
    "resolve_web_search_execution_context",
]
