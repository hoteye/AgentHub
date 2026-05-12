from __future__ import annotations

import time
from typing import Any

from cli.agent_cli.runtime_core import (
    provider_catalog_commands_normalization_helpers_runtime as normalization_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_catalog_commands_projection_helpers_runtime as projection_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_catalog_commands_pure_helpers_runtime as pure_helpers_runtime,
)


def _provider_loader_kwargs(agent: Any) -> dict[str, Any]:
    return normalization_helpers_runtime.provider_loader_kwargs(agent)


def _load_catalog(runtime: Any) -> tuple[Any, dict[str, Any]]:
    return normalization_helpers_runtime.load_catalog(runtime)


def _provider_aliases(runtime: Any, catalog: Any) -> tuple[dict[str, set[str]], dict[str, str]]:
    return normalization_helpers_runtime.provider_aliases(runtime, catalog)


def _ttl_seconds_from_provider(entry: Any) -> int:
    return pure_helpers_runtime.ttl_seconds_from_provider(entry)


def _resolve_provider_targets(
    runtime: Any,
    *,
    catalog: Any,
    provider_filter: str,
) -> tuple[list[str] | None, str | None, dict[str, str]]:
    return normalization_helpers_runtime.resolve_provider_targets(
        runtime,
        catalog=catalog,
        provider_filter=provider_filter,
    )


def _provider_display_name(public_by_config: dict[str, str], provider_name: str) -> str:
    return normalization_helpers_runtime.provider_display_name(public_by_config, provider_name)


def handle_models_refresh_command(runtime: Any, *, arg_text: str) -> tuple[str, list[Any]]:
    from cli.agent_cli import provider_catalog_runtime

    provider_filter = str(arg_text or "").strip()
    try:
        catalog, loader_kwargs = _load_catalog(runtime)
    except Exception as exc:
        return (projection_helpers_runtime.models_refresh_unavailable_text(error=exc), [])
    targets, resolve_error, public_by_config = _resolve_provider_targets(
        runtime,
        catalog=catalog,
        provider_filter=provider_filter,
    )
    if targets is None:
        return (
            projection_helpers_runtime.models_refresh_usage_error(error=resolve_error or ""),
            [],
        )
    cache_path = provider_catalog_runtime.remote_model_catalog_cache_path(cwd=loader_kwargs.get("cwd"))
    lines = projection_helpers_runtime.models_refresh_header_lines(
        provider_filter=provider_filter,
        cache_path=cache_path,
    )
    refreshed = 0
    fallback = 0
    skipped = 0
    for provider_name in targets:
        provider_entry = getattr(catalog, "providers", {}).get(provider_name)
        raw_provider = dict(getattr(provider_entry, "raw_provider", {}) or {})
        endpoint = str(raw_provider.get("catalog_endpoint") or "").strip()
        display_name = _provider_display_name(public_by_config, provider_name)
        ttl_seconds = _ttl_seconds_from_provider(provider_entry)
        if not endpoint:
            skipped += 1
            lines.append(
                projection_helpers_runtime.models_refresh_skipped_line(
                    display_name=display_name,
                    ttl_seconds=ttl_seconds,
                )
            )
            continue
        try:
            result = provider_catalog_runtime.refresh_remote_model_catalog(
                provider_name=provider_name,
                catalog_endpoint=endpoint,
                cwd=loader_kwargs.get("cwd"),
                ttl_seconds=ttl_seconds,
                force=True,
            )
        except Exception as exc:
            models = []
            try:
                models = list(
                    provider_catalog_runtime.load_cached_remote_models(
                        provider_name=provider_name,
                        cwd=loader_kwargs.get("cwd"),
                    )
                    or []
                )
            except Exception:
                models = []
            fallback += 1
            lines.append(
                projection_helpers_runtime.models_refresh_fallback_line(
                    display_name=display_name,
                    error=exc,
                    model_count=len(models),
                    ttl_seconds=ttl_seconds,
                )
            )
            continue
        status = str(result.get("status") or "-").strip() or "-"
        model_count = len(list(result.get("models") or []))
        if status == "fallback_cached":
            fallback += 1
        else:
            refreshed += 1
        error_text = str(result.get("error") or "").strip()
        lines.append(
            projection_helpers_runtime.models_refresh_result_line(
                display_name=display_name,
                status=status,
                cache_hit=bool(result.get("cache_hit")),
                model_count=model_count,
                ttl_seconds=ttl_seconds,
                error_text=error_text,
            )
        )
    lines.extend(
        projection_helpers_runtime.models_refresh_summary_lines(
            providers=len(targets),
            refreshed=refreshed,
            fallback_cached=fallback,
            skipped=skipped,
        )
    )
    return ("\n".join(lines), [])


def _cache_freshness(*, fetched_at: int, expires_at: int, model_count: int, now: int) -> str:
    return pure_helpers_runtime.cache_freshness(
        fetched_at=fetched_at,
        expires_at=expires_at,
        model_count=model_count,
        now=now,
    )


def handle_models_cache_status_command(runtime: Any, *, arg_text: str) -> tuple[str, list[Any]]:
    from cli.agent_cli.providers import model_catalog_cache_runtime

    provider_filter = str(arg_text or "").strip()
    try:
        catalog, loader_kwargs = _load_catalog(runtime)
    except Exception as exc:
        return (projection_helpers_runtime.models_cache_status_unavailable_text(error=exc), [])
    targets, resolve_error, public_by_config = _resolve_provider_targets(
        runtime,
        catalog=catalog,
        provider_filter=provider_filter,
    )
    if targets is None:
        return (
            projection_helpers_runtime.models_cache_status_usage_error(error=resolve_error or ""),
            [],
        )
    cache_path = model_catalog_cache_runtime.default_cache_path(cwd=loader_kwargs.get("cwd"))
    payload = model_catalog_cache_runtime.read_cache(cache_path)
    now = int(time.time())
    lines = projection_helpers_runtime.models_cache_status_header_lines(
        provider_filter=provider_filter,
        cache_path=cache_path,
    )
    for provider_name in targets:
        provider_entry = getattr(catalog, "providers", {}).get(provider_name)
        raw_provider = dict(getattr(provider_entry, "raw_provider", {}) or {})
        has_endpoint = bool(str(raw_provider.get("catalog_endpoint") or "").strip())
        cached_entry = model_catalog_cache_runtime.provider_cache_entry(payload, provider_name)
        models = cached_entry.get("models")
        model_count = pure_helpers_runtime.cached_model_count(models)
        fetched_at = int(cached_entry.get("fetched_at") or 0)
        expires_at = int(cached_entry.get("expires_at") or 0)
        configured_ttl = _ttl_seconds_from_provider(provider_entry)
        cache_ttl = pure_helpers_runtime.cache_ttl_seconds(
            fetched_at=fetched_at,
            expires_at=expires_at,
            configured_ttl=configured_ttl,
        )
        ttl_remaining = pure_helpers_runtime.ttl_remaining_seconds(
            expires_at=expires_at,
            now=now,
        )
        freshness = _cache_freshness(
            fetched_at=fetched_at,
            expires_at=expires_at,
            model_count=model_count,
            now=now,
        )
        display_name = _provider_display_name(public_by_config, provider_name)
        lines.append(
            projection_helpers_runtime.models_cache_status_line(
                display_name=display_name,
                freshness=freshness,
                ttl_seconds=cache_ttl,
                ttl_remaining_seconds=ttl_remaining,
                model_count=model_count,
                has_endpoint=has_endpoint,
            )
        )
    lines.extend(
        projection_helpers_runtime.models_cache_status_summary_lines(
            providers=len(targets),
        )
    )
    return ("\n".join(lines), [])
